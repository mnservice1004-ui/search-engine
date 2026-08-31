import hashlib
import importlib.util
import shutil
import sqlite3
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "validate_task_contacts_migration.py"
SCHEMA_PATH = ROOT / "sql" / "task_contacts_schema.sql"

SPEC = importlib.util.spec_from_file_location("validate_task_contacts_migration", SCRIPT_PATH)
assert SPEC and SPEC.loader
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def make_baseline_db(path: Path, synthetic_contact_dataset) -> Path:
    shutil.copy2(synthetic_contact_dataset.db, path)
    return path


@pytest.fixture(scope="module")
def temporary_trial(tmp_path_factory, synthetic_contact_dataset):
    directory = tmp_path_factory.mktemp("task-contacts-trial")
    source_db = make_baseline_db(directory / "baseline.db", synthetic_contact_dataset)
    before_sha256 = file_sha256(source_db)
    report = MIGRATION.run_temporary_trial(
        source_db=source_db,
        workbook=synthetic_contact_dataset.workbook,
        tasks_path=synthetic_contact_dataset.tasks,
        schema_path=SCHEMA_PATH,
        expected_workbook_sha256=synthetic_contact_dataset.workbook_sha256,
        contact_matches_path=directory / "contact_matches.json",
    )
    return report, before_sha256, file_sha256(source_db)


def test_schema_is_reentrant_and_enforces_the_1_to_many_contract(
    tmp_path, synthetic_contact_dataset
):
    db_path = make_baseline_db(tmp_path / "schema-contract.db", synthetic_contact_dataset)
    with sqlite3.connect(db_path, isolation_level=None) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        try:
            MIGRATION.migrate_schema(connection, SCHEMA_PATH)
            MIGRATION.migrate_schema(connection, SCHEMA_PATH)
            connection.commit()
        except Exception:
            connection.rollback()
            raise

        columns = {row[1] for row in connection.execute("PRAGMA table_info(task_contacts)")}
        assert {
            "task_id",
            "phone",
            "display_phone",
            "label",
            "note",
            "contact_role",
            "condition_text",
            "is_primary",
            "source_url",
            "source_sheet",
            "source_row",
            "verified_at",
            "match_status",
            "active",
        }.issubset(columns)

        foreign_keys = connection.execute("PRAGMA foreign_key_list(task_contacts)").fetchall()
        assert any(
            row[2] == "tasks" and row[3] == "task_id" and row[4] == "id" for row in foreign_keys
        )
        primary_index = connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'index' AND name = 'idx_task_contacts_one_active_primary'
            """
        ).fetchone()[0]
        assert "WHERE is_primary = 1 AND active = 1" in primary_index


def test_schema_rejects_an_incompatible_existing_primary_index(
    tmp_path, synthetic_contact_dataset
):
    db_path = make_baseline_db(tmp_path / "incompatible-schema.db", synthetic_contact_dataset)
    with sqlite3.connect(db_path, isolation_level=None) as connection:
        connection.execute("BEGIN IMMEDIATE")
        MIGRATION.migrate_schema(connection, SCHEMA_PATH)
        connection.commit()
        connection.execute("DROP INDEX idx_task_contacts_one_active_primary")
        connection.execute(
            """
            CREATE UNIQUE INDEX idx_task_contacts_one_active_primary
            ON task_contacts(task_id)
            WHERE is_primary = 0 AND active = 1
            """
        )
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(MIGRATION.TrialValidationError, match="partial UNIQUE"):
            MIGRATION.migrate_schema(connection, SCHEMA_PATH)
        connection.rollback()


def test_official_url_validation_rejects_suffix_tricks_and_userinfo():
    assert MIGRATION.is_official_hscity_url("https://www.hscity.go.kr/health/")
    assert MIGRATION.is_official_hscity_url("https://hscity.go.kr/")
    assert not MIGRATION.is_official_hscity_url("https://evilhscity.go.kr/")
    assert not MIGRATION.is_official_hscity_url("https://hscity.go.kr@example.com/")
    assert not MIGRATION.is_official_hscity_url("http://www.hscity.go.kr/")


def test_temporary_trial_stages_only_approved_contacts(temporary_trial):
    report, before_sha256, after_sha256 = temporary_trial
    counts = report["counts"]
    validation = report["temporary_database"]["second_validation"]

    assert report["validation_passed"] is True
    assert report["errors"] == []
    assert counts == {
        "staging_task_count": 51,
        "actual_contact_row_count": 93,
        "primary_contact_row_count": 45,
        "confirmed_multiple_task_count": 9,
        "conditional_task_count": 11,
        "held_task_count": 12,
        "tasks_with_multiple_contact_rows": 20,
    }
    assert validation["total_contact_rows"] == 93
    assert validation["staging_task_count"] == 51
    assert validation["duplicate_count"] == 0
    assert validation["primary_duplicate_count"] == 0
    assert validation["orphan_task_id_count"] == 0
    assert before_sha256 == after_sha256
    assert report["live_database"]["writes"] == 0


def test_core_contacts_are_separate_rows_with_the_required_primary(temporary_trial):
    report, _, _ = temporary_trial
    core = report["temporary_database"]["core_contacts"]

    for task_id in ("A011", "F101"):
        assert [(row["phone"], row["is_primary"]) for row in core[task_id]] == [
            ("031-5189-4364", 1)
        ]

    assert {
        (row["phone"], row["label"], row["is_primary"])
        for row in core["A012"]
    } == {
        ("031-5189-4364", "대표전화", 1),
        ("031-5189-4344", "흉부 X선", 0),
        ("031-5189-4369", "검체검사", 0),
        ("031-5189-4368", "진단검사실", 0),
        ("031-5189-4377", "민원접수", 0),
    }
    assert all(
        row["phone"] != "031-5189-4354"
        for task_rows in core.values()
        for row in task_rows
    )


def test_phone_notes_are_not_used_as_contact_purposes(temporary_trial):
    report, _, _ = temporary_trial
    by_task = report["temporary_database"]["contacts_by_task"]

    for task_id in ("M006", "M009"):
        row = next(row for row in by_task[task_id] if row["phone"] == "031-5189-5023")
        assert row["note"] == "기존 근거"
        assert row["label"] != "기존 근거"
    m009 = next(
        row for row in by_task["M009"] if row["phone"] == "031-5189-5023"
    )
    assert m009["condition_text"] != "기존 근거"


def test_idempotence_constraints_and_forced_rollback(temporary_trial):
    report, _, _ = temporary_trial
    temporary = report["temporary_database"]

    assert temporary["first_apply"] == {"inserted": 93, "updated": 0}
    assert temporary["second_apply"] == {"inserted": 0, "updated": 93}
    assert temporary["idempotence"] == {
        "row_count_unchanged": True,
        "logical_sha256_unchanged": True,
        "sequence_unchanged": True,
        "passed": True,
    }
    assert temporary["rollback"] == {
        "forced_failure_seen": True,
        "state_unchanged": True,
        "passed": True,
    }
    assert all(temporary["constraints"].values())
    assert temporary["core_tables_unchanged"] is True


def test_sqlite_integrity_checks_pass_and_temporary_copy_is_removed(temporary_trial):
    report, _, _ = temporary_trial
    temporary = report["temporary_database"]
    validation = temporary["second_validation"]

    assert validation["foreign_key_check"] == []
    assert validation["integrity_check"] == ["ok"]
    assert temporary["deleted_after_test"] is True
    assert not Path(temporary["path_during_test"]).exists()


def test_backup_api_refuses_to_overwrite_its_source(tmp_path, synthetic_contact_dataset):
    source_db = make_baseline_db(tmp_path / "protected-source.db", synthetic_contact_dataset)
    with pytest.raises(MIGRATION.TrialValidationError, match="운영 DB"):
        MIGRATION.backup_database(source_db, source_db)
