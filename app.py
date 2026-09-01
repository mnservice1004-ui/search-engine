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
from sms_service import send_contact_sms


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
PUBLIC_GUIDANCE = load_public_guidance()

app = Flask(__name__, static_folder="public", static_url_path="")
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


def _public_rank_key(task):
    return (
        -int(task.get("_public_match_tier") or 0),
        -int(task.get("score") or 0),
        -int(task.get("priority") or 0),
        str(task.get("name") or ""),
        str(task.get("id") or ""),
    )


def search_public_tasks(searchable_tasks, query, limit=100):
    ranked = search_tasks(searchable_tasks, query, 100)
    for task in ranked:
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
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "task_count": len(get_all_tasks()),
        "data_backend": os.getenv("DATA_BACKEND", "sqlite"),
        "llm_enabled": os.getenv("ENABLE_LLM", "false").lower() == "true",
        "sms_mode": os.getenv("SMS_MODE", "mock"),
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

    tasks = get_all_tasks()
    searchable_tasks = build_public_search_tasks(tasks, PUBLIC_GUIDANCE)
    all_results = search_public_tasks(searchable_tasks, query, 100)
    expansions = []
    if not all_results and _allow_query_expansion(query):
        expansions = expand_query(query)
        merged = {}
        for expanded in expansions:
            for item in search_public_tasks(searchable_tasks, expanded, 100):
                previous = merged.get(item["id"])
                if previous is None or _public_rank_key(item) < _public_rank_key(previous):
                    merged[item["id"]] = item
        all_results = sorted(merged.values(), key=_public_rank_key)

    items = attach_public_contacts(all_results[:10])
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
    })


@app.get("/api/tasks/<task_id>")
def task_detail(task_id):
    task = get_task(task_id)
    if task is None:
        return jsonify({"error": "업무를 찾을 수 없습니다."}), 404
    return jsonify(attach_public_contacts([task])[0])


@app.post("/api/sms")
@limiter.limit("3 per minute")
def send_sms():
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
        return jsonify({"error": "허용되지 않은 요청 출처입니다."}), 403
    payload = request.get_json(silent=True) or {}
    if payload.get("consent") is not True:
        return jsonify({"error": "문자 전송을 위한 휴대전화번호 이용에 동의해야 합니다."}), 400
    task = get_task(str(payload.get("task_id", "")))
    if task is None:
        return jsonify({"error": "업무를 찾을 수 없습니다."}), 404
    task = attach_public_contacts([task])[0]
    try:
        result = send_contact_sms(task, payload.get("recipient"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "문자 발송 서비스가 응답하지 않습니다. 잠시 후 다시 시도하십시오."}), 502
    best_effort_log("sms_success", task_id=task["id"])
    return jsonify(result)


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
