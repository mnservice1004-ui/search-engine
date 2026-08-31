import copy
import json
from pathlib import Path

import pytest

from public_guidance import (
    EXPECTED_TASK_IDS,
    PUBLIC_CONTACT_FIELDS,
    PUBLIC_TEXT_FIELDS,
    PublicGuidanceConfigurationError,
    load_public_guidance,
    serialize_public_task,
)


ROOT = Path(__file__).resolve().parents[1]
GUIDANCE_PATH = ROOT / "data" / "public_guidance.json"


def write_payload(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def base_payload():
    return json.loads(GUIDANCE_PATH.read_text(encoding="utf-8"))


PHONE_TEST_PATHS = (
    ("tasks", 0, "public_summary"),
    ("tasks", 0, "eligibility"),
    ("tasks", 1, "visit_steps"),
    ("tasks", 1, "public_caution"),
    ("tasks", 2, "primary_action"),
    ("tasks", 2, "organization", "department"),
    ("tasks", 2, "location", "route_text"),
)


BLOCKED_PHONE_LIKE_VALUES = (
    "031-5189-5032",
    "031 5189 5032",
    "031.5189.5032",
    "(031) 5189-5032",
    "03151895032",
    "tel:031-5189-5032",
    "+82-31-5189-5032",
    "+82 31 5189 5032",
    "+82 (0)31 5189 5032",
    "0082-31-5189-5032",
    "+823151895032",
    "82-31-5189-5032",
    "＋８２－３１－５１８９－５０３２",
    "+82–31–5189–5032",
    "+82-31-5189-5032",
    "문의는 +82-31-5189-5032로 해 주세요.",
    "010-1234-5678",
    "+82-10-1234-5678",
    "1588-1234",
    "내선 5032",
    "문의: 5032",
    "031\u200b5189\u20605032",
    "031\u00a05189\u00a05032",
)


ALLOWED_NON_PHONE_VALUES = (
    "2026-08-28",
    "2026.08.28",
    "2026년 8월 28일",
    "20260828",
    "65세 이상 어르신",
    "6개월 동안 건강관리를 받습니다.",
    "1층",
    "3층",
    "A011",
    "A012",
    "R002",
    "A011·A012·R002",
    "A011 — 2026-08-28",
    "업무 63건",
    "검색 결과는 최대 10개입니다.",
    "오전 9시부터 오후 6시까지",
    "1:1 건강관리",
    "방문 장소는 전화로 확인해 주세요.",
)


def set_nested(payload, path, value):
    target = payload
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value


def test_checked_in_public_guidance_has_exact_three_task_contract(monkeypatch, tmp_path):
    guidance = load_public_guidance(GUIDANCE_PATH)

    assert set(guidance) == EXPECTED_TASK_IDS
    for task_id, item in guidance.items():
        assert item["task_id"] == task_id
        assert set(PUBLIC_TEXT_FIELDS) <= set(item)
        serialized = json.dumps(item, ensure_ascii=False)
        assert "031-" not in serialized
        for forbidden in ("note", "source", "status", "source_row", "hash", "local_path"):
            assert forbidden not in serialized

    r002 = guidance["R002"]
    assert r002["organization"] == {
        "department": "건강증진과",
        "team": "지역보건팀",
    }
    assert r002["location"] == {
        "floor": None,
        "room": None,
        "route_text": "방문 장소는 전화로 확인해 주세요.",
        "show_map": False,
    }
    monkeypatch.chdir(tmp_path)
    assert set(load_public_guidance()) == EXPECTED_TASK_IDS


def test_guidance_missing_or_invalid_json_fails_closed(tmp_path):
    with pytest.raises(PublicGuidanceConfigurationError, match="missing"):
        load_public_guidance(tmp_path / "missing.json")

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not-json", encoding="utf-8")
    with pytest.raises(PublicGuidanceConfigurationError, match="cannot be read"):
        load_public_guidance(invalid)

    payload = base_payload()
    payload.update({"schema_version": 1.0})
    with pytest.raises(PublicGuidanceConfigurationError):
        load_public_guidance(write_payload(tmp_path / "float-schema.json", payload))


@pytest.mark.parametrize(
    ("case_index", "phone_like"),
    tuple(enumerate(BLOCKED_PHONE_LIKE_VALUES)),
)
def test_phone_like_values_are_rejected_recursively(tmp_path, case_index, phone_like):
    payload = base_payload()
    path = PHONE_TEST_PATHS[case_index % len(PHONE_TEST_PATHS)]
    set_nested(payload, path, phone_like)

    with pytest.raises(PublicGuidanceConfigurationError) as caught:
        load_public_guidance(write_payload(tmp_path / f"blocked-{case_index}.json", payload))

    message = str(caught.value)
    assert message.startswith("phone-like value is not allowed at root.tasks[")
    assert phone_like not in message
    assert not any(number in message for number in ("5032", "5678", "1234"))


@pytest.mark.parametrize(
    ("case_index", "allowed_value"),
    tuple(enumerate(ALLOWED_NON_PHONE_VALUES)),
)
def test_non_phone_values_are_allowed_recursively(tmp_path, case_index, allowed_value):
    payload = base_payload()
    path = PHONE_TEST_PATHS[case_index % len(PHONE_TEST_PATHS)]
    set_nested(payload, path, allowed_value)

    guidance = load_public_guidance(
        write_payload(tmp_path / f"allowed-{case_index}.json", payload)
    )
    assert set(guidance) == EXPECTED_TASK_IDS


@pytest.mark.parametrize(
    "mutate",
    (
        lambda payload: payload.update({"unexpected": True}),
        lambda payload: payload["tasks"][0].update({"unexpected": True}),
        lambda payload: payload["tasks"].append(copy.deepcopy(payload["tasks"][0])),
        lambda payload: payload.update({"schema_version": True}),
        lambda payload: payload["tasks"][0]["location"].update({"show_map": "yes"}),
        lambda payload: payload["tasks"][2]["location"].update({"floor": "3층"}),
        lambda payload: payload["tasks"][0]["location"].update({"floor": None}),
        lambda payload: payload["tasks"][2]["location"].update({"x": 42}),
        lambda payload: payload["tasks"][0].update({"verified_date": "2026/08/28"}),
    ),
)
def test_guidance_schema_errors_are_rejected(tmp_path, mutate):
    payload = base_payload()
    mutate(payload)

    with pytest.raises(PublicGuidanceConfigurationError):
        load_public_guidance(write_payload(tmp_path / "invalid.json", payload))


def test_duplicate_json_object_key_is_rejected(tmp_path):
    duplicate = GUIDANCE_PATH.read_text(encoding="utf-8").replace(
        '"schema_version": 1,',
        '"schema_version": 1,\n  "schema_version": 1,',
        1,
    )
    path = tmp_path / "duplicate-key.json"
    path.write_text(duplicate, encoding="utf-8")

    with pytest.raises(PublicGuidanceConfigurationError, match="duplicate JSON key"):
        load_public_guidance(path)


def test_unregistered_task_uses_allowlist_instead_of_raw_task_copy():
    raw = {
        "id": "R003",
        "name": "연명치료",
        "department": "건강증진과",
        "team": "지역보건팀",
        "floor": "1층",
        "place": "재활보건실",
        "route": "1층으로 가세요.",
        "question": "문의가 필요한가요?",
        "caution": "전화로 확인해 주세요.",
        "script": "안내를 받으세요.",
        "status": "must-not-leak",
        "source": "must-not-leak",
        "note": "must-not-leak",
        "source_hash": "must-not-leak",
        "local_path": "C:/must-not-leak",
        "review_state": "must-not-leak",
        "raw_payload": {"must": "not leak"},
        "phone": "031-999-9999",
        "aliases": [{"text": "연명치료", "weight": 10, "type": "search"}],
        "score": 321,
    }
    contacts = [
        {
            "phone": "031-5189-0000",
            "display_phone": "031-5189-0000",
            "purpose": "대표전화",
            "role": "문의",
            "condition": None,
            "verified_date": "2026-08-28",
            "is_primary": True,
            "status": "must-not-leak",
            "source_row": 99,
        }
    ]

    item = serialize_public_task(raw, contacts, load_public_guidance(GUIDANCE_PATH))
    serialized = json.dumps(item, ensure_ascii=False)

    assert item["id"] == "R003"
    assert item["score"] == 321
    assert item["show_map"] is True
    assert set(item["contacts"][0]) == set(PUBLIC_CONTACT_FIELDS)
    for forbidden in (
        '"status"',
        '"source"',
        '"note"',
        '"source_hash"',
        '"local_path"',
        '"review_state"',
        '"raw_payload"',
        '"phone": "031-999-9999"',
    ):
        assert forbidden not in serialized
