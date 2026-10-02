import json
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from db import get_all_tasks, get_contacts_by_task_ids, get_task, log_event
from llm_helper import expand_query
from public_guidance import (
    build_public_search_tasks,
    build_public_suggestion_tasks,
    load_public_guidance,
    serialize_public_task,
)
from search_engine import normalize, search_tasks, suggest_terms
from vaccination import search_vaccination
from examinations import search_examinations
from official_services import search_official_services, menu_guide_ids
from sms_service import send_contact_sms, build_message, sms_capability, SmsConfigurationError, SmsDeliveryError


ROOT = Path(__file__).resolve().parent
if os.getenv('VERCEL') != '1':
    load_dotenv(ROOT / ".env")
PUBLIC_GUIDANCE = load_public_guidance()

app = Flask(__name__, static_folder=None if os.getenv('VERCEL') == '1' else 'public', static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024
if os.getenv('VERCEL') == '1':
    # Vercel is the sole trusted edge; do not trust forwarded headers locally.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=0)
limiter = Limiter(get_remote_address, app=app, default_limits=["120 per minute"], storage_uri="memory://")


def best_effort_log(event_type, task_id=None, result_count=None):
    try:
        log_event(event_type, task_id=task_id, result_count=result_count)
    except Exception:
        # 이용 통계 실패가 검색이나 이미 접수된 문자 발송 결과를 뒤집지 않게 한다.
        app.logger.warning("비식별 이벤트 로그 기록 실패: %s", event_type)


def attach_public_contacts(tasks):
    contacts_by_task = get_contacts_by_task_ids(task.get("id") for task in tasks)
    public_tasks = []
    for task in tasks:
        task_id = str(task.get("id") or "")
        public_tasks.append(
            serialize_public_task(
                task,
                contacts_by_task.get(task_id, []),
                PUBLIC_GUIDANCE,
            )
        )
    return public_tasks


def _public_match_tier(task, query):
    guidance = PUBLIC_GUIDANCE.get(str(task.get("id") or ""))
    if not guidance:
        return 0
    normalized_query = normalize(query)
    if normalized_query == normalize(guidance["public_title"]):
        return 2
    if any(
        normalized_query == normalize(term)
        for term in guidance["public_search_terms"]
    ):
        return 1
    return 0


def _map_point_for_place(map_points, floor, place):
    points = map_points.get(str(floor or ""), {})
    if place in points:
        return points[place]
    matches = [
        point
        for name, point in points.items()
        if name not in {"start", "정문"}
        and (str(place or "") in name or name in str(place or ""))
    ]
    return matches[0] if len(matches) == 1 else None


def build_verified_map_target_registry(tasks, map_points):
    """Map exact, verified floor-plan terms to their location-guide task IDs."""

    registry = {}
    ambiguous_terms = set()
    for task in tasks:
        place = str(task.get("place") or "")
        name = str(task.get("name") or "")
        if not place or normalize(name) != normalize(f"{place} 위치 안내"):
            continue
        point = _map_point_for_place(map_points, task.get("floor"), place)
        if not point or point.get("review_status") != "verified_floorplan_label":
            continue
        terms = [place, point.get("printed_label")]
        terms.extend(
            alias.get("text")
            for alias in task.get("aliases", [])
            if alias.get("type") == "장소어"
        )
        for term in terms:
            normalized_term = normalize(term)
            if not normalized_term or normalized_term in ambiguous_terms:
                continue
            previous_task_id = registry.get(normalized_term)
            if previous_task_id and previous_task_id != task.get("id"):
                registry.pop(normalized_term, None)
                ambiguous_terms.add(normalized_term)
                continue
            registry[normalized_term] = task.get("id")
    return registry


def _exact_map_location_task_id(query, map_target_registry):
    normalized_query = normalize(query)
    if normalized_query in map_target_registry:
        return map_target_registry[normalized_query]
    for suffix in ("위치", "어디"):
        if normalized_query.endswith(suffix):
            task_id = map_target_registry.get(normalized_query[: -len(suffix)])
            if task_id:
                return task_id
    return None


def _public_rank_key(task):
    return (
        -int(task.get("_map_location_match_tier") or 0),
        -int(task.get("_public_match_tier") or 0),
        -int(task.get("score") or 0),
        -int(task.get("priority") or 0),
        str(task.get("name") or ""),
        str(task.get("id") or ""),
    )


def search_public_tasks(searchable_tasks, query, limit=100, map_target_registry=None):
    ranked = search_tasks(searchable_tasks, query, 100)
    exact_location_task_id = _exact_map_location_task_id(
        query, map_target_registry or {}
    )
    if exact_location_task_id and not any(
        task.get("id") == exact_location_task_id for task in ranked
    ):
        location_task = next(
            (
                task for task in searchable_tasks
                if task.get("id") == exact_location_task_id
            ),
            None,
        )
        if location_task is not None:
            ranked.append({**location_task, "score": 0})
    for task in ranked:
        task["_map_location_match_tier"] = int(
            task.get("id") == exact_location_task_id
        )
        task["_public_match_tier"] = _public_match_tier(task, query)
    ranked.sort(key=_public_rank_key)
    return ranked[: max(1, min(int(limit), 100))]


def _allow_query_expansion(query):
    normalized_query = normalize(query)
    return (
        "인바디" not in normalized_query
        and "13주" not in normalized_query
    )


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; base-uri 'self'; "
        "object-src 'none'; form-action 'self'; frame-ancestors 'none'"
    )
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.get("/")
def index():
    return send_from_directory(ROOT / 'public', "index.html")


@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "task_count": len(get_all_tasks()),
        "data_backend": os.getenv("DATA_BACKEND", "sqlite"),
        "llm_enabled": os.getenv("ENABLE_LLM", "false").lower() == "true",
        "sms_mode": sms_capability()['mode'],
    })


@app.get("/api/map-points")
def map_points():
    path = ROOT / "data" / "map_points.json"
    return jsonify(json.loads(path.read_text(encoding="utf-8")))


@app.post("/api/suggestions")
def suggestions():
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query", "")).strip()
    if len(query) > 80:
        return jsonify({"error": "검색어는 80자 이하여야 합니다."}), 400
    tasks = build_public_suggestion_tasks(get_all_tasks(), PUBLIC_GUIDANCE)
    return jsonify({"items": suggest_terms(tasks, query)})


@app.post("/api/search")
@limiter.limit("60 per minute")
def search():
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query", "")).strip()
    if not 2 <= len(query) <= 80:
        return jsonify({"error": "검색어를 2~80자로 입력하십시오."}), 400

    # Legacy callers retain their top-10 contract. The result directory opts
    # into all ranked records so category counts and pagination are truthful.
    limit = payload.get("limit", 10)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        return jsonify({"error": "검색 결과 수는 1~100 사이의 정수여야 합니다."}), 400

    tasks = get_all_tasks()
    searchable_tasks = build_public_search_tasks(tasks, PUBLIC_GUIDANCE)
    map_points = json.loads((ROOT / "data" / "map_points.json").read_text(encoding="utf-8"))
    map_target_registry = build_verified_map_target_registry(tasks, map_points)
    # A short cancer intent must not inherit unrelated "진단"/"검사" task
    # matches. Reviewed guides below supply the relevant existing task link.
    cancer_intent = normalize(query)
    cancer_queries = {'암진단', '암진단검사', '암진단지원', '암검진', '암검진검사'}
    all_results = [] if cancer_intent in cancer_queries else search_public_tasks(
        searchable_tasks, query, 100, map_target_registry
    )
    guide_query = cancer_intent if cancer_intent in {'암진단', '암검진'} else query
    menu_ids = menu_guide_ids(query)
    vaccination = search_vaccination(guide_query, region='dongtan', source_scope='current', include_ids=menu_ids)
    examinations = search_examinations(guide_query, include_ids=menu_ids)
    services = search_official_services(guide_query, include_ids=menu_ids)
    # Explicitly reviewed relationships extend discovery without changing the
    # permanent catalog, contact ownership, maps or public task schema.
    matched_guides = ([g for g in vaccination['guides'] if not g['expired']] + examinations['guides']
                      + [g for g in services['guides'] if not g['expired']])
    matched_ids = {item['id'] for item in all_results}
    by_id = {item['id']: item for item in searchable_tasks}
    for guide in matched_guides:
        for task_id in guide['related_task_ids']:
            if task_id in by_id and task_id not in matched_ids:
                all_results.append({**by_id[task_id], 'score': 0})
                matched_ids.add(task_id)
    expansions = []
    if not all_results and cancer_intent not in cancer_queries and _allow_query_expansion(query):
        expansions = expand_query(query)
        merged = {}
        for expanded in expansions:
            for item in search_public_tasks(searchable_tasks, expanded, 100):
                previous = merged.get(item["id"])
                if previous is None or _public_rank_key(item) < _public_rank_key(previous):
                    merged[item["id"]] = item
        all_results = sorted(merged.values(), key=_public_rank_key)

    items = attach_public_contacts(all_results[:limit])
    best_effort_log("search", result_count=len(all_results))
    return jsonify({
        "query": query,
        "total": len(all_results),
        "returned_count": len(items),
        "results": items,
        "total_count": len(all_results),
        "displayed_count": len(items),
        "items": items,
        "expanded_terms": expansions,
        "vaccination": vaccination,
        "examinations": examinations,
        "services": services,
    })


@app.post("/api/vaccination/search")
@limiter.limit("60 per minute")
def vaccination_search():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "검색 조건을 확인하십시오."}), 400
    query = str(payload.get("query", "")).strip()
    page = payload.get("page", 1)
    kind = payload.get("kind", "sources")
    region = payload.get("region", "dongtan")
    source_scope = payload.get("source_scope", "current")
    if (not 2 <= len(query) <= 80 or kind not in ("sources", "facilities")
            or region not in ('dongtan', 'all') or source_scope not in ('current', 'archive', 'all')
            or isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 1000):
        return jsonify({"error": "검색어와 페이지를 확인하십시오."}), 400
    return jsonify(search_vaccination(query, kind=kind, page=page, region=region, source_scope=source_scope))


@app.get("/api/tasks/<task_id>")
def task_detail(task_id):
    task = get_task(task_id)
    if task is None:
        return jsonify({"error": "업무를 찾을 수 없습니다."}), 404
    return jsonify(attach_public_contacts([task])[0])


@app.get("/api/services")
def services():
    # Same public serializer as search/detail: never expose raw task records,
    # internal aliases or unverified contacts through the HOME directory.
    items = attach_public_contacts(get_all_tasks())
    return jsonify({"results": items, "total": len(items)})


@app.post("/api/sms")
@limiter.limit("3 per minute")
def send_sms():
    origin = request.headers.get("Origin")
    if os.getenv('VERCEL') == '1':
        from sms_cloud_guard import allowed_origin
        if not allowed_origin(origin):
            return jsonify({'error': '허용되지 않았거나 아직 설정되지 않은 발송 출처입니다.'}), 403
    if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
        return jsonify({"error": "허용되지 않은 요청 출처입니다."}), 403
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "올바른 요청 형식이 아닙니다."}), 400
    if payload.get("consent") is not True:
        return jsonify({"error": "문자 전송을 위한 휴대전화번호 이용에 동의해야 합니다."}), 400
    task = get_task(str(payload.get("task_id", "")))
    if task is None:
        return jsonify({"error": "업무를 찾을 수 없습니다."}), 404
    task = attach_public_contacts([task])[0]
    guidance = PUBLIC_GUIDANCE.get(task["id"])
    if guidance is not None:
        # 문자용 필드 선택은 공개 API 응답에 노출하지 않고 서버 안에서만 사용한다.
        task["_sms_fields"] = list(guidance["sms_fields"])
    try:
        if "message_kind" in payload or "request_id" in payload:
            cloud_options = ({'client_ip': request.headers.get('X-Forwarded-For', '').strip()}
                             if os.getenv('VERCEL') == '1' else {})
            result = send_contact_sms(task, payload.get("recipient"), payload.get("message_kind", "combined"), payload.get("request_id"), **cloud_options)
        else:
            result = send_contact_sms(task, payload.get("recipient"))
    except SmsConfigurationError as exc:
        return jsonify({"error": str(exc)}), 503
    except SmsDeliveryError as exc:
        return jsonify({"error": str(exc)}), 502
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "문자 발송 서비스가 응답하지 않습니다. 잠시 후 다시 시도하십시오."}), 502
    best_effort_log("sms_success", task_id=task["id"])
    return jsonify(result)


@app.post("/api/sms/preview")
@limiter.limit("30 per minute")
def sms_preview():
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
        return jsonify({"error": "허용되지 않은 요청 출처입니다."}), 403
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "올바른 요청 형식이 아닙니다."}), 400
    raw = get_task(str(payload.get("task_id", "")))
    if raw is None:
        return jsonify({"error": "업무를 찾을 수 없습니다."}), 404
    task = attach_public_contacts([raw])[0]
    guidance = PUBLIC_GUIDANCE.get(task['id'])
    if guidance:
        task['_sms_fields'] = list(guidance['sms_fields'])
    try:
        text = build_message(task, payload.get('message_kind', 'guidance'))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"text": text, **sms_capability()})


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
