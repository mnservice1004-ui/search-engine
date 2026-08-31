import os
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


@pytest.fixture(scope="module")
def temporary_api_db(tmp_path_factory, synthetic_contact_dataset):
    destination_path = tmp_path_factory.mktemp("api-database") / "health_search.db"
    shutil.copy2(synthetic_contact_dataset.populated_db, destination_path)
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
