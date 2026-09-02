import json
import os
import re
import shutil
from hashlib import sha256
from pathlib import Path

import pytest


os.environ["DATA_BACKEND"] = "sqlite"
os.environ["SQLITE_PATH"] = "__pytest_requires_synthetic_contact_fixture__.db"
os.environ["ENABLE_LLM"] = "false"
os.environ["SMS_MODE"] = "mock"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

from app import app  # noqa: E402
from public_guidance import EXPECTED_TASK_IDS  # noqa: E402
from sms_service import send_contact_sms  # noqa: E402


FORBIDDEN_PUBLIC_KEYS = {
    "note",
    "source",
    "status",
    "source_row",
    "source_hash",
    "local_path",
}
FORBIDDEN_PUBLIC_KEY_FRAGMENTS = (
    "review",
    "raw",
    "admin",
    "validator",
    "관리자",
    "검수자",
)
FORBIDDEN_PUBLIC_VALUE_FRAGMENTS = (
    "c:/users/",
    "c:\\users\\",
    "source_row",
    "source_sheet",
    "source_url",
    "raw_payload",
    "review_state",
    "sha256",
    "원문기준",
    "검수 메모",
    "자료 출처",
    "내부 메모",
    "[공식 확인 필요]",
)
FIRST_BATCH_CONTACTS = {
    "A001": ("031-5189-4378",),
    "A019": ("031-5189-4344",),
    "H001": ("031-5189-4371",),
    "H002": ("031-5189-4374",),
    "M002": ("031-5189-6944",),
    "M003": ("031-5189-6943", "031-5189-4370", "031-5189-5085"),
    "M004": ("031-5189-4370", "031-5189-5085", "031-5189-6944"),
    "M005": ("031-5189-6944", "031-5189-4370", "031-5189-5085"),
    "M006": (
        "031-5189-6944",
        "031-5189-4370",
        "031-5189-5085",
        "031-5189-5023",
    ),
    "M008": ("031-5189-6944",),
}
FIRST_BATCH_LOCATIONS = {
    "A001": ("1층", "진료실", True),
    "A019": ("1층", "영상의학실", True),
    "H001": ("2층", "금연상담실", True),
    "H002": ("2층", "만성질환관리센터", True),
    "M002": (None, None, False),
    "M003": (None, None, False),
    "M004": (None, None, False),
    "M005": (None, None, False),
    "M006": (None, None, False),
    "M008": (None, None, False),
}
SEARCH_REGRESSION_CASES = {
    "A007": (
        "방역·소독 문의",
        "위생해충 방제",
        "소독 의무시설 서류",
        "소독업 신고",
    ),
    "A019": ("골다공증 검사를 받고 싶으신가요?", "골다공증 검사", "골밀도 검사"),
    "H001": ("담배를 끊는 상담을 받고 싶으신가요?", "금연 상담", "금연클리닉"),
    "H002": (
        "만성질환 위험군 건강관리",
        "만성질환 건강관리",
        "운동 영양 상담",
        "만성질환 건강상담",
    ),
    "A001": ("보건소 진료를 받고 싶으신가요?", "보건소 진료", "진료 접수"),
    "M002": ("아기의 선천성대사이상 지원이 필요하신가요?", "선천성대사이상 의료비 지원"),
    "M003": ("난임 시술비 지원을 신청하고 싶으신가요?", "체외수정 지원", "인공수정 지원"),
    "M004": ("산모·신생아 건강관리 지원을 신청하고 싶으신가요?", "산후도우미 지원"),
    "M005": ("고위험 임산부 의료비 지원이 필요하신가요?", "고위험 임신질환 지원"),
    "M006": ("아기 기저귀·조제분유 지원을 신청하고 싶으신가요?", "기저귀 바우처"),
    "M008": ("미숙아·선천성이상아 의료비 지원이 필요하신가요?", "미숙아 의료비 지원"),
}
H002_FORBIDDEN_PUBLIC_FRAGMENTS = (
    "인바디",
    "13주",
    "근로자",
    "무료",
    "09:00",
    "18:00",
)


def assert_no_internal_public_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.casefold()
            assert key not in FORBIDDEN_PUBLIC_KEYS
            assert not any(fragment in normalized for fragment in FORBIDDEN_PUBLIC_KEY_FRAGMENTS)
            assert_no_internal_public_keys(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_internal_public_keys(item)


def assert_no_internal_public_values(value):
    if isinstance(value, dict):
        for item in value.values():
            assert_no_internal_public_values(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_internal_public_values(item)
    elif isinstance(value, str):
        normalized = value.casefold().replace("\\", "/")
        assert not any(fragment in normalized for fragment in FORBIDDEN_PUBLIC_VALUE_FRAGMENTS)
        assert re.search(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", normalized) is None


@pytest.fixture(scope="module")
def temporary_api_db(tmp_path_factory, public_guidance_contact_db):
    destination_path = tmp_path_factory.mktemp("api-database") / "health_search.db"
    shutil.copy2(public_guidance_contact_db, destination_path)
    return destination_path


@pytest.fixture(autouse=True)
def configure_test_database_and_disable_logging(monkeypatch, temporary_api_db):
    monkeypatch.setenv("DATA_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(temporary_api_db))
    monkeypatch.setenv("ENABLE_LLM", "false")
    monkeypatch.setenv("SMS_MODE", "mock")
    monkeypatch.setattr("app.log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.expand_query", lambda _query: [])


def client():
    app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    return app.test_client()


def test_health_and_no_store_header():
    response = client().get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["task_count"] == 63
    assert response.headers["Cache-Control"].startswith("no-store")


def test_homepage_uses_dongtan_gu_branding():
    response = client().get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "<title>동탄구보건소 보건민원 정보 검색</title>" in html
    assert "동탄구보건소" in html
    assert "보건민원 길찾기" in html
    assert 'src="/images/hwaseong-special-city-bi.png"' in html
    assert 'alt="화성특례시"' in html
    assert 'aria-label="화성특례시 홈페이지"' in html
    assert 'href="https://www.hscity.go.kr/"' in html
    assert "공식 업무자료 기반 안내" not in html
    assert "가까운 보건소 업무 안내" not in html
    assert "찾고 싶은 보건민원을" in html
    assert "말하듯 검색하세요" in html
    assert "필요한 업무와 담당 부서, 찾아가는 위치까지 한 화면에서 안내해 드립니다." in html
    assert "오늘의 하늘처럼, 민원 안내도 맑고 편안하게" in html
    assert 'href="https://www.hscity.go.kr/health/index.do"' in html
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html
    assert '<p id="status" class="sr-only" role="status" aria-live="polite">' in html

    required_ids = (
        "query", "search-button", "clear-button", "suggestions", "status", "results",
        "floor-label", "floor-image", "map-marker", "map-label", "route-text", "detail",
        "detail-dialog", "detail-dialog-title", "close-detail",
        "sms-dialog", "sms-form", "recipient", "consent", "sms-status", "cancel-sms", "send-sms",
    )
    for element_id in required_ids:
        assert html.count(f'id="{element_id}"') == 1

    for query in ("연명치료", "예방접종", "산후도우미", "건강진단서"):
        assert f'data-query="{query}"' in html

    detail_dialog_start = html.index('<dialog id="detail-dialog"')
    detail_dialog_end = html.index("</dialog>", detail_dialog_start)
    detail_dialog_html = html[detail_dialog_start:detail_dialog_end]
    for element_id in ("floor-image", "map-marker", "map-label", "route-text", "detail"):
        assert f'id="{element_id}"' in detail_dialog_html
    for floor in ("1층", "2층", "3층"):
        assert f'data-floor="{floor}"' in detail_dialog_html


def test_hero_asset_and_screenshot_layout_css():
    hero = Path("public/images/hero-dongtan.jpg")
    content = hero.read_bytes()
    css = Path("public/css/style.css").read_text(encoding="utf-8")

    assert len(content) == 2310012
    assert content.startswith(b"\xff\xd8\xff")
    assert sha256(content).hexdigest() == "ec53099e0e40ace51ab9c384bd93cd4318f749a67613e5786323eff7b5aa4c6e"
    assert 'url("/images/hero-dongtan.jpg")' in css
    assert "background-size:cover" in css
    assert "min-height:100svh" in css
    assert "width:min(1180px" in css
    assert "width:min(980px" in css
    assert ".hero-stage::before" in css
    assert "prefers-reduced-motion:reduce" in css


def test_frontend_script_opens_details_only_after_result_selection():
    script = Path("public/js/app.js").read_text(encoding="utf-8")

    assert "showDetail(items[0])" not in script
    assert "detailDialogEl.showModal()" in script
    assert "detailDialogEl.close()" in script
    assert "aria-haspopup" in script
    assert "aria-controls" in script


def test_frontend_contact_renderer_uses_safe_text_and_digit_only_tel_links():
    script = Path("public/js/app.js").read_text(encoding="utf-8")

    assert "function appendPublicContacts(container, contacts)" in script
    assert "contact.display_phone || contact.phone" in script
    assert "replace(/\\D/g, '')" in script
    assert "link.href = `tel:${telDigits}`" in script
    assert "contact.is_primary" in script
    assert "contact.purpose" in script
    assert "contact.condition" in script
    assert "innerHTML" not in script
    assert "task.primary_contact?.phone" in script
    assert "const verifiedContact = task.primary_contact || contacts.find((contact) => contact.is_primary);" in script
    assert "verifiedContact?.verified_date" in script
    assert "task.contact_verified_at" not in script
    assert "showMap(task);" in script
    assert "task?.show_map === false" in script
    assert "task.source" not in script
    assert "task.note" not in script
    assert "task.status" not in script
    assert "task.contact_name" not in script
    assert "task.contact_role" not in script


@pytest.mark.parametrize(
    ("path", "content_type"),
    (
        ("/css/style.css", "text/css"),
        ("/js/app.js", "text/javascript"),
        ("/images/hero-dongtan.jpg", "image/jpeg"),
        ("/images/hwaseong-special-city-bi.png", "image/png"),
        ("/images/floor-1.jpg", "image/jpeg"),
        ("/images/floor-2.jpg", "image/jpeg"),
        ("/images/floor-3.jpg", "image/jpeg"),
    ),
)
def test_static_assets_are_served(path, content_type):
    response = client().get(path)

    assert response.status_code == 200
    assert response.content_type.startswith(content_type)


def test_search_post_returns_expected_first_item():
    response = client().post("/api/search", json={"query": "연명치료"})
    body = response.get_json()
    assert response.status_code == 200
    assert body["total_count"] >= 1
    assert body["items"][0]["id"] == "R003"
    assert "primary_contact" in body["items"][0]
    assert "contacts" in body["items"][0]
    assert body["results"] == body["items"]
    assert body["total"] == body["total_count"]
    assert body["returned_count"] == body["displayed_count"] == len(body["items"])
    assert len(body["results"]) <= 10
    assert body["total"] >= body["returned_count"]


def test_search_api_returns_only_public_contact_fields_for_core_tasks():
    response = client().post("/api/search", json={"query": "결핵"})
    items = {item["id"]: item for item in response.get_json()["items"]}
    public_fields = {
        "phone",
        "display_phone",
        "purpose",
        "role",
        "condition",
        "verified_date",
        "is_primary",
    }

    assert response.status_code == 200
    for task_id in ("A011", "A012", "F101"):
        assert task_id in items
        assert all(set(contact) == public_fields for contact in items[task_id]["contacts"])
        assert all(contact["phone"] != "031-5189-4354" for contact in items[task_id]["contacts"])
        assert items[task_id]["primary_contact"] in items[task_id]["contacts"]

    assert len(items["A011"]["contacts"]) == 1
    assert items["A011"]["primary_contact"]["phone"] == "031-5189-4364"
    assert len(items["F101"]["contacts"]) == 1
    assert items["F101"]["primary_contact"]["phone"] == "031-5189-4364"
    assert len(items["A012"]["contacts"]) == 5
    assert sum(contact["is_primary"] for contact in items["A012"]["contacts"]) == 1
    assert items["A012"]["contacts"] == sorted(
        items["A012"]["contacts"],
        key=lambda contact: (
            0 if contact["is_primary"] else 1,
            contact["purpose"].casefold(),
            contact["phone"],
        ),
    )
    assert {
        (contact["phone"], contact["purpose"], contact["is_primary"])
        for contact in items["A012"]["contacts"]
    } == {
        ("031-5189-4364", "대표전화", True),
        ("031-5189-4344", "흉부 X선", False),
        ("031-5189-4369", "검체검사", False),
        ("031-5189-4368", "진단검사실", False),
        ("031-5189-4377", "민원접수", False),
    }
    assert items["A012"]["primary_contact"] == items["A012"]["contacts"][0]


def test_search_and_task_detail_never_expose_internal_task_fields():
    search_response = client().post("/api/search", json={"query": "연명치료"})
    detail_response = client().get("/api/tasks/R003")

    assert search_response.status_code == 200
    assert detail_response.status_code == 200
    assert_no_internal_public_keys(search_response.get_json())
    assert_no_internal_public_keys(detail_response.get_json())


def test_representative_public_guidance_and_map_contracts():
    a011 = client().get("/api/tasks/A011").get_json()
    a012 = client().get("/api/tasks/A012").get_json()
    r002_response = client().post("/api/search", json={"query": "어르신 오늘 건강"})
    r002 = r002_response.get_json()["items"][0]

    assert r002_response.status_code == 200
    assert r002["id"] == "R002"
    assert (a011["floor"], a011["room"], a011["show_map"]) == (
        "1층",
        "결핵실",
        True,
    )
    assert a011["place"] == a011["room"]
    assert (a012["floor"], a012["room"], a012["show_map"]) == (
        "1층",
        "민원실",
        True,
    )
    assert a012["place"] == a012["room"]
    assert a011["primary_contact"]["phone"] == "031-5189-4364"
    assert len(a012["contacts"]) == 5
    assert all(contact["phone"] != "031-5189-4354" for contact in a012["contacts"])

    assert r002["department"] == "건강증진과"
    assert r002["team"] == "지역보건팀"
    assert r002["floor"] is None
    assert r002["place"] is None
    assert r002["room"] is None
    assert r002["show_map"] is False
    assert r002["route"] == "방문 장소는 전화로 확인해 주세요."
    assert "65세 이상" in r002["public_summary"]
    assert "6개월" in r002["public_summary"]
    assert r002["documents"] is None
    assert r002["fee"] is None
    assert r002["operating_hours"] is None
    serialized = str(r002)
    for forbidden in ("보건행정과", "3층", "원문기준", "검수 메모", "자료 출처", "무료", "현재 모집 중"):
        assert forbidden not in serialized
    assert_no_internal_public_keys(r002)


@pytest.mark.parametrize("task_id", tuple(FIRST_BATCH_CONTACTS))
def test_first_batch_api_guidance_contacts_and_location_contract(task_id):
    response = client().get(f"/api/tasks/{task_id}")
    item = response.get_json()
    expected_phones = FIRST_BATCH_CONTACTS[task_id]
    floor, room, show_map = FIRST_BATCH_LOCATIONS[task_id]

    assert response.status_code == 200
    assert item["id"] == task_id
    assert item["public_title"] == item["name"]
    assert item["public_summary"]
    assert item["eligibility"]
    assert item["primary_action"]
    assert item["verified_date"] == "2026-08-26"
    assert (item["floor"], item["room"], item["show_map"]) == (
        floor,
        room,
        show_map,
    )
    assert item["place"] == room
    if show_map:
        assert floor in item["route"]
        assert room in item["route"]
    else:
        assert item["route"] == "방문 장소는 전화로 확인해 주세요."

    assert item["primary_contact"] == item["contacts"][0]
    assert item["primary_contact"]["phone"] == expected_phones[0]
    assert item["primary_contact"]["is_primary"] is True
    assert {contact["phone"] for contact in item["contacts"]} == set(expected_phones)
    assert sum(contact["is_primary"] for contact in item["contacts"]) == 1
    assert all(contact["verified_date"] == "2026-08-28" for contact in item["contacts"])
    assert all(
        set(contact)
        == {
            "phone",
            "display_phone",
            "purpose",
            "role",
            "condition",
            "verified_date",
            "is_primary",
        }
        for contact in item["contacts"]
    )
    assert_no_internal_public_keys(item)
    assert_no_internal_public_values(item)


def test_remaining_forty_nine_task_details_stay_available_without_internal_projection():
    tasks = json.loads(Path("data/tasks.json").read_text(encoding="utf-8"))
    remaining_ids = [task["id"] for task in tasks if task["id"] not in EXPECTED_TASK_IDS]

    assert len(remaining_ids) == 49
    for task_id in remaining_ids:
        response = client().get(f"/api/tasks/{task_id}")
        item = response.get_json()
        assert response.status_code == 200
        assert item["id"] == task_id
        assert item["aliases"] == []
        assert all(item[field] is None for field in (
            "public_title",
            "public_summary",
            "eligibility",
            "documents",
            "fee",
            "operating_hours",
            "visit_steps",
            "public_caution",
            "primary_action",
            "verified_date",
        ))
        assert_no_internal_public_keys(item)
        assert_no_internal_public_values(item)


def test_r002_detail_preserves_five_contacts_without_public_metadata(monkeypatch):
    phones = (
        "031-5189-5032",
        "031-5189-4778",
        "031-5189-4779",
        "031-5189-6933",
        "031-5189-6946",
    )

    def contact_loader(task_ids):
        task_ids = list(task_ids)
        return {
            task_id: [
                {
                    "phone": phone,
                    "display_phone": phone,
                    "purpose": "원문 행 46 내부 검수",
                    "role": "동탄3·5·6동 방문건강관리",
                    "condition": "internal-review-file.xlsx",
                    "verified_date": "2026-08-28",
                    "is_primary": index == 0,
                    "status": "must-not-leak",
                    "source_row": 999,
                }
                for index, phone in enumerate(phones)
            ]
            if task_id == "R002"
            else [
                {
                    "phone": "031-5189-4364",
                    "display_phone": "031-5189-4364",
                    "purpose": "internal-review-file.xlsx",
                    "role": "C:/private/review.xlsx",
                    "condition": "a" * 64,
                    "verified_date": "2026-08-28",
                    "is_primary": True,
                }
            ]
            if task_id == "A011"
            else []
            for task_id in task_ids
        }

    monkeypatch.setattr("app.get_contacts_by_task_ids", contact_loader)
    response = client().get("/api/tasks/R002")
    item = response.get_json()

    assert response.status_code == 200
    assert [contact["phone"] for contact in item["contacts"]] == list(phones)
    assert sum(contact["is_primary"] for contact in item["contacts"]) == 1
    assert item["primary_contact"] == item["contacts"][0]
    assert item["primary_contact"]["phone"] == "031-5189-5032"
    assert item["primary_contact"]["purpose"] == "대표전화"
    assert item["primary_contact"]["role"] == "어르신 건강관리 문의"
    assert item["primary_contact"]["condition"] is None
    assert all(
        contact["purpose"] == "권역별 방문건강 문의"
        and contact["role"] is None
        and contact["condition"] == "담당 지역은 대표전화로 확인해 주세요."
        for contact in item["contacts"][1:]
    )
    serialized = str(item)
    for forbidden in ("원문 행", "내부 검수", "동탄3·5·6동", "internal-review-file.xlsx"):
        assert forbidden not in serialized
    assert_no_internal_public_keys(item)

    a011 = client().get("/api/tasks/A011").get_json()
    assert a011["primary_contact"]["purpose"] == "연락처"
    assert a011["primary_contact"]["role"] is None
    assert a011["primary_contact"]["condition"] is None
    assert "C:/private" not in str(a011)
    assert "a" * 64 not in str(a011)
    assert_no_internal_public_keys(a011)


def test_held_task_has_no_public_contacts():
    response = client().post("/api/search", json={"query": "금연아파트 지정"})
    item = next(item for item in response.get_json()["items"] if item["id"] == "H004")

    assert response.status_code == 200
    assert item["primary_contact"] is None
    assert item["contacts"] == []


def test_search_uses_one_bulk_contact_lookup(monkeypatch):
    from app import get_contacts_by_task_ids as original_loader

    calls = []

    def counted_loader(task_ids):
        task_ids = list(task_ids)
        calls.append(task_ids)
        return original_loader(task_ids)

    monkeypatch.setattr("app.get_contacts_by_task_ids", counted_loader)
    response = client().post("/api/search", json={"query": "결핵"})

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0] == [item["id"] for item in response.get_json()["items"]]
    assert len(calls[0]) <= 10


def test_first_batch_search_regression_and_single_contact_batch(monkeypatch):
    from app import (
        PUBLIC_GUIDANCE,
        get_contacts_by_task_ids as original_loader,
        search_public_tasks,
    )
    from db import get_all_tasks
    from public_guidance import build_public_search_tasks

    calls = []

    def counted_loader(task_ids):
        task_ids = list(task_ids)
        calls.append(task_ids)
        return original_loader(task_ids)

    monkeypatch.setattr("app.get_contacts_by_task_ids", counted_loader)
    raw_tasks = get_all_tasks()
    searchable_tasks = build_public_search_tasks(raw_tasks, PUBLIC_GUIDANCE)
    for expected_id, queries in SEARCH_REGRESSION_CASES.items():
        for query in queries:
            call_count = len(calls)
            expected_ranked = search_public_tasks(searchable_tasks, query, 10)
            response = client().post("/api/search", json={"query": query})
            body = response.get_json()

            assert response.status_code == 200
            assert expected_ranked[0]["id"] == expected_id
            assert body["items"][0]["id"] == expected_id
            assert [item["id"] for item in body["items"]] == [
                item["id"] for item in expected_ranked
            ]
            assert len(body["results"]) <= 10
            assert body["returned_count"] == len(body["results"])
            assert body["total"] >= body["returned_count"]
            assert len(calls) == call_count + 1
            assert calls[-1] == [item["id"] for item in body["items"]]


def test_search_rejects_short_query():
    response = client().post("/api/search", json={"query": "검"})
    assert response.status_code == 400


def test_unknown_search_is_empty():
    response = client().post("/api/search", json={"query": "완전히없는검색어"})
    assert response.status_code == 200
    assert response.get_json()["total_count"] == 0


def test_sms_requires_consent():
    response = client().post(
        "/api/sms",
        json={"task_id": "R003", "recipient": "01000000000", "consent": False},
    )
    assert response.status_code == 400


def test_sms_blocks_task_without_primary_contact():
    response = client().post(
        "/api/sms",
        json={"task_id": "H004", "recipient": "01000000000", "consent": True},
    )
    assert response.status_code == 400
    assert "공식 담당 연락처" in response.get_json()["error"]


def test_sms_mock_preview_uses_dongtan_gu_branding(monkeypatch):
    monkeypatch.setenv("SMS_MODE", "mock")
    task = {
        "name": "예방접종 문의",
        "department": "보건행정과",
        "team": "감염병관리팀",
        "contact_name": "홍길동",
        "contact_role": "주무관",
        "phone": "031-999-9999",
        "primary_contact": {
            "phone": "031-000-0000",
            "display_phone": "031-000-0000",
            "verified_date": "2026-08-28",
        },
    }

    result = send_contact_sms(task, "010-1234-5678")

    assert result["status"] == "mocked"
    assert result["provider"] == "mock"
    assert result["preview"].startswith("[동탄구보건소 민원안내]\n")
    assert "전화: 031-000-0000" in result["preview"]
    assert "031-999-9999" not in result["preview"]
    assert "[동탄보건소 민원안내]" not in result["preview"]


def test_sms_mock_endpoint_uses_primary_contact(monkeypatch):
    monkeypatch.setenv("SMS_MODE", "mock")

    response = client().post(
        "/api/sms",
        json={"task_id": "A011", "recipient": "01012345678", "consent": True},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "mocked"
    assert response.get_json()["preview"].startswith("[동탄구보건소 민원안내]\n")
    assert "전화: 031-5189-4364" in response.get_json()["preview"]


def test_a007_api_and_sms_use_runtime_primary_without_internal_location(monkeypatch):
    monkeypatch.setenv("SMS_MODE", "mock")
    response = client().get("/api/tasks/A007")
    item = response.get_json()

    assert response.status_code == 200
    assert item["public_title"] == "방역·소독 업무를 문의하시나요?"
    assert item["primary_contact"] == item["contacts"][0]
    assert item["primary_contact"]["phone"] == "031-5189-5093"
    assert item["primary_contact"]["is_primary"] is True
    assert len(item["contacts"]) == 1
    assert item["verified_date"] == "2026-08-26"
    assert (item["floor"], item["room"], item["show_map"]) == (
        None,
        None,
        False,
    )
    assert item["route"] == "방문 장소는 전화로 확인해 주세요."
    assert item["aliases"] == [
        "방역·소독 업무를 문의하시나요?",
        "위생해충 방제 문의",
        "소독 의무시설 서류 제출",
        "소독업 신고 준비 안내",
    ]
    assert_no_internal_public_keys(item)
    assert_no_internal_public_values(item)

    preview = send_contact_sms(item, "01012345678")["preview"]
    assert "전화: 031-5189-5093" in preview
    assert "방문 장소는 전화로 확인해 주세요." in preview
    assert "3층" not in preview
    assert "031-5189-5093" not in json.dumps(
        json.loads(Path("data/public_guidance.json").read_text(encoding="utf-8"))["tasks"],
        ensure_ascii=False,
    )


def test_sms_does_not_fall_back_to_legacy_task_phone():
    task = {
        "name": "보류 업무",
        "department": "건강증진과",
        "phone": "031-999-9999",
        "primary_contact": None,
    }

    with pytest.raises(ValueError, match="공식 담당 연락처"):
        send_contact_sms(task, "01012345678")


def test_sms_uses_only_public_guidance_and_primary_contact(monkeypatch):
    monkeypatch.setenv("SMS_MODE", "mock")
    task = {
        "name": "내부 업무명",
        "public_title": "65세 이상 건강관리 서비스를 찾으시나요?",
        "public_summary": "65세 이상 어르신이 스마트폰과 건강기기를 이용해 6개월 동안 건강관리를 받을 수 있는 사업입니다.",
        "department": "건강증진과",
        "team": "지역보건팀",
        "route": "방문 장소는 전화로 확인해 주세요.",
        "verified_date": "2026-08-28",
        "primary_contact": {
            "phone": "031-5189-5032",
            "display_phone": "031-5189-5032",
            "verified_date": "2026-08-28",
        },
        "note": "검수 메모",
        "source": "자료 출처",
        "status": "원문기준",
        "contact_name": "내부 담당자",
        "contact_role": "내부 직위",
        "floor": "3층",
        "place": "보건행정과",
        "phone": "031-999-9999",
    }

    preview = send_contact_sms(task, "01012345678")["preview"]

    assert "031-5189-5032" in preview
    assert "65세 이상" in preview
    assert "6개월" in preview
    assert "건강증진과 / 지역보건팀" in preview
    assert "방문 장소는 전화로 확인해 주세요." in preview
    for forbidden in (
        "검수 메모",
        "자료 출처",
        "원문기준",
        "내부 담당자",
        "내부 직위",
        "보건행정과",
        "3층",
        "031-999-9999",
        "무료",
        "현재 모집 중",
    ):
        assert forbidden not in preview


@pytest.mark.parametrize("task_id", ("M003", "M008"))
def test_no_map_public_guidance_sms_uses_phone_confirmation_route(task_id, monkeypatch):
    monkeypatch.setenv("SMS_MODE", "mock")
    detail = client().get(f"/api/tasks/{task_id}").get_json()

    preview = send_contact_sms(detail, "01012345678")["preview"]

    assert "방문 장소는 전화로 확인해 주세요." in preview
    assert detail["primary_contact"]["phone"] in preview
    assert "모자보건실·예방접종실" not in preview
    assert "건강증진과 사무실" not in preview
    assert "3층" not in preview
    assert_no_internal_public_values(preview)


def test_h002_public_api_detail_and_sms_omit_unverified_claims(monkeypatch):
    monkeypatch.setenv("SMS_MODE", "mock")
    search_response = client().post(
        "/api/search", json={"query": "만성질환 건강관리"}
    )
    search_item = next(
        item for item in search_response.get_json()["items"] if item["id"] == "H002"
    )
    detail_response = client().get("/api/tasks/H002")
    detail = detail_response.get_json()
    preview = send_contact_sms(detail, "01012345678")["preview"]

    assert search_response.status_code == 200
    assert detail_response.status_code == 200
    for value in (search_item, detail, preview):
        serialized = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        assert not any(
            fragment in serialized for fragment in H002_FORBIDDEN_PUBLIC_FRAGMENTS
        )


def test_public_aliases_are_safe_terms_and_unregistered_aliases_are_empty():
    from app import PUBLIC_GUIDANCE

    for task_id, guidance in PUBLIC_GUIDANCE.items():
        item = client().get(f"/api/tasks/{task_id}").get_json()
        assert item["aliases"] == guidance["public_search_terms"]
        assert all(isinstance(alias, str) for alias in item["aliases"])

    unregistered = client().get("/api/tasks/R003").get_json()
    assert unregistered["aliases"] == []


@pytest.mark.parametrize("query", ("인바디", "13주", "13주 프로그램"))
def test_h002_internal_aliases_cannot_return_h002_or_trigger_llm_expansion(
    query, monkeypatch
):
    monkeypatch.setattr(
        "app.expand_query", lambda _query: ["만성질환 건강관리"]
    )

    response = client().post("/api/search", json={"query": query})
    body = response.get_json()

    assert response.status_code == 200
    assert "H002" not in {item["id"] for item in body["items"]}
    assert body["expanded_terms"] == []


def test_suggestions_use_public_terms_without_internal_aliases():
    public_response = client().post(
        "/api/suggestions", json={"query": "만성질환"}
    )
    forbidden_response = client().post(
        "/api/suggestions", json={"query": "인바디"}
    )

    assert public_response.status_code == 200
    assert "만성질환 건강관리" in public_response.get_json()["items"]
    assert forbidden_response.status_code == 200
    assert "인바디" not in " ".join(forbidden_response.get_json()["items"])


def test_corrected_public_guidance_claims_reach_task_detail_api():
    a019 = client().get("/api/tasks/A019").get_json()
    m002 = client().get("/api/tasks/M002").get_json()
    m008 = client().get("/api/tasks/M008").get_json()

    assert "6,000원" in a019["fee"]
    assert "검사비는 변동될 수" in a019["public_caution"]
    assert "대상 영아의 부모가" in m002["eligibility"]
    assert "영아가 신청" not in m002["eligibility"]
    assert "출생일로부터 1년 이내" in m002["eligibility"]
    assert "출생 후 24시간 이내" in m008["eligibility"]
    assert "긴급한 수술이나 치료가 필요" in m008["eligibility"]
    assert "신생아 중환자실(NICU)에 입원" in m008["eligibility"]
    assert m008["fee"] is None
    assert (m002["floor"], m002["room"], m002["show_map"]) == (None, None, False)
    assert (m008["floor"], m008["room"], m008["show_map"]) == (None, None, False)
