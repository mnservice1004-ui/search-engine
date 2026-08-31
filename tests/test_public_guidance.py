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

    for name, mutate in (
        ("float-schema", lambda payload: payload.update({"schema_version": 1.0})),
        (
            "obfuscated-phone",
            lambda payload: payload["tasks"][0].update(
                {"primary_action": "(031) 5189.4364로 전화하세요."}
            ),
        ),
    ):
        payload = base_payload()
        mutate(payload)
        with pytest.raises(PublicGuidanceConfigurationError):
            load_public_guidance(write_payload(tmp_path / f"{name}.json", payload))


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
        lambda payload: payload["tasks"][0].update(
            {"primary_action": "031-5189-4364로 전화하세요."}
        ),
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
