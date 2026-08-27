import os
from hashlib import sha256
from pathlib import Path

import pytest


os.environ["DATA_BACKEND"] = "sqlite"
os.environ["SQLITE_PATH"] = "data/health_search.db"
os.environ["ENABLE_LLM"] = "false"
os.environ["SMS_MODE"] = "mock"

from app import app  # noqa: E402
from sms_service import send_contact_sms  # noqa: E402


@pytest.fixture(autouse=True)
def disable_event_logging(monkeypatch):
    monkeypatch.setattr("app.log_event", lambda *args, **kwargs: None)


def client():
    app.config.update(TESTING=True)
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


def test_sms_blocks_unverified_contact():
    response = client().post(
        "/api/sms",
        json={"task_id": "R003", "recipient": "01000000000", "consent": True},
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
        "phone": "031-000-0000",
        "contact_verified_at": "2026-08-27",
    }

    result = send_contact_sms(task, "010-1234-5678")

    assert result["status"] == "mocked"
    assert result["provider"] == "mock"
    assert result["preview"].startswith("[동탄구보건소 민원안내]\n")
    assert "[동탄보건소 민원안내]" not in result["preview"]


def test_sms_mock_endpoint_accepts_verified_task(monkeypatch):
    task = {
        "id": "T-MOCK",
        "name": "예방접종 문의",
        "department": "보건행정과",
        "team": "감염병관리팀",
        "contact_name": "홍길동",
        "contact_role": "주무관",
        "phone": "031-000-0000",
        "contact_verified_at": "2026-08-27",
    }
    monkeypatch.setattr("app.get_task", lambda task_id: task if task_id == task["id"] else None)
    monkeypatch.setenv("SMS_MODE", "mock")

    response = client().post(
        "/api/sms",
        json={"task_id": task["id"], "recipient": "01012345678", "consent": True},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "mocked"
    assert response.get_json()["preview"].startswith("[동탄구보건소 민원안내]\n")
