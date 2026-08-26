import os


os.environ["DATA_BACKEND"] = "sqlite"
os.environ["SQLITE_PATH"] = "data/health_search.db"
os.environ["ENABLE_LLM"] = "false"
os.environ["SMS_MODE"] = "mock"

from app import app  # noqa: E402


def client():
    app.config.update(TESTING=True)
    return app.test_client()


def test_health_and_no_store_header():
    response = client().get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["task_count"] == 63
    assert response.headers["Cache-Control"].startswith("no-store")


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
