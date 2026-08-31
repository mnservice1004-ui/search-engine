import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "import_confirmed_contacts.py"
SPEC = importlib.util.spec_from_file_location("import_confirmed_contacts", SCRIPT_PATH)
assert SPEC and SPEC.loader
IMPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORTER)


def file_sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_phone_parser_separates_notes_and_expands_only_explicit_shorthand():
    assert IMPORTER.parse_phone_entries("031-5189-5023(기존 근거)") == [
        {
            "phone": "031-5189-5023",
            "note": "기존 근거",
            "raw": "031-5189-5023(기존 근거)",
        }
    ]
    assert [
        item["phone"]
        for item in IMPORTER.parse_phone_entries("031-5189-4369·4368(진단검사실 검사 수행)")
    ] == ["031-5189-4369", "031-5189-4368"]
    assert IMPORTER.parse_phone_entries("25번 번호는 잘림") == []
    assert IMPORTER.find_unparsed_phone_fragments("031-5189-502") == ["031-5189-502"]


def test_synthetic_workbook_dry_run_is_complete_and_does_not_write(
    synthetic_contact_dataset, tmp_path, capsys
):
    workbook_path = synthetic_contact_dataset.workbook
    tasks_path = synthetic_contact_dataset.tasks
    db_path = synthetic_contact_dataset.db
    output_path = tmp_path / "contact_matches.json"
    before = {
        "workbook": file_sha256(workbook_path),
        "tasks": file_sha256(tasks_path),
        "db": file_sha256(db_path),
    }

    exit_code = IMPORTER.main(
        [
            "--workbook",
            str(workbook_path),
            "--tasks",
            str(tasks_path),
            "--db",
            str(db_path),
            "--expected-sha256",
            synthetic_contact_dataset.workbook_sha256,
            "--output",
            str(output_path),
            "--format",
            "json",
        ]
    )
    report = json.loads(capsys.readouterr().out)
    after = {
        "workbook": file_sha256(workbook_path),
        "tasks": file_sha256(tasks_path),
        "db": file_sha256(db_path),
    }

    assert exit_code == 0
    assert report["validation_passed"] is True
    assert report["id_reconciliation"]["excel_count"] == 63
    assert report["id_reconciliation"]["matched_count"] == 63
    assert report["status_counts"] == IMPORTER.EXPECTED_STATUS_COUNTS
    assert report["summary"]["primary_phone_new_or_changed_count"] == 45
    assert report["summary"]["multiple_contact_count"] == 9
    assert report["summary"]["conditional_contact_count"] == 11
    assert report["summary"]["held_for_review_count"] == 12
    assert before == after
    assert not output_path.exists()


def test_core_changes_and_hold_policy_use_no_guessed_primary(synthetic_contact_dataset):
    payload, report = IMPORTER.run_import(
        synthetic_contact_dataset.workbook,
        synthetic_contact_dataset.tasks,
        synthetic_contact_dataset.db,
        expected_sha256=synthetic_contact_dataset.workbook_sha256,
    )
    matches = {item["task_id"]: item for item in payload["matches"]}

    assert report["validation_passed"] is True
    assert matches["M005"]["primary_phone"] == "031-5189-6944"
    assert matches["M007"]["primary_phone"] == "031-5189-5076"
    assert {item["phone"] for item in matches["M007"]["contacts"]} == {
        "031-5189-5076",
        "031-5189-5075",
        "031-5189-4370",
        "031-5189-5085",
    }
    assert (matches["R002"]["department"], matches["R002"]["team"]) == (
        "건강증진과",
        "지역보건팀",
    )
    assert matches["R002"]["primary_phone"] == "031-5189-5032"
    assert (matches["A005"]["department"], matches["A005"]["team"]) == (
        "건강증진과",
        "모자보건팀",
    )
    assert matches["A005"]["primary_phone"] == "031-5189-5076"

    assert matches["H004"]["primary_phone"] is None
    assert matches["H004"]["contacts"]
    assert not any(item["is_primary"] for item in matches["H004"]["contacts"])
    assert matches["F206"]["primary_phone"] is None
    assert matches["F206"]["contacts"] == []
    for task_id in ("A011", "F101"):
        assert matches[task_id]["match_status"] == "confirmed"
        assert matches[task_id]["primary_phone"] == "031-5189-4364"
        assert "결핵" in matches[task_id]["contacts"][0]["role"]
    assert all(
        next(item for item in match["contacts"] if item["is_primary"])["role"]
        for match in matches.values()
        if match["match_status"] in {"confirmed", "confirmed_multiple"}
    )
    assert all(
        item["condition_text"]
        for match in matches.values()
        if match["match_status"] == "conditional"
        for item in match["contacts"]
    )


def test_workbook_hash_is_pinned(synthetic_contact_dataset):
    with pytest.raises(IMPORTER.ValidationError, match="SHA-256 불일치"):
        IMPORTER.run_import(
            synthetic_contact_dataset.workbook,
            synthetic_contact_dataset.tasks,
            synthetic_contact_dataset.db,
            expected_sha256="0" * 64,
        )


def test_write_target_cannot_replace_an_input_or_existing_json(
    synthetic_contact_dataset, tmp_path
):
    workbook_path = synthetic_contact_dataset.workbook
    tasks_path = synthetic_contact_dataset.tasks
    db_path = synthetic_contact_dataset.db
    existing_json = tmp_path / "existing.json"
    existing_json.write_text("{}\n", encoding="utf-8")

    assert "덮어쓸 수 없습니다" in IMPORTER.validate_output_path(
        db_path, (workbook_path, tasks_path, db_path), force=True
    )
    assert "--force 필요" in IMPORTER.validate_output_path(
        existing_json, (workbook_path, tasks_path, db_path), force=False
    )
    assert IMPORTER.validate_output_path(
        existing_json, (workbook_path, tasks_path, db_path), force=True
    ) is None
