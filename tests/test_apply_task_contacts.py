import hashlib
import importlib.util
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "apply_task_contacts.py"
SOURCE_SCHEMA = ROOT / "sql" / "task_contacts_schema.sql"

SPEC = importlib.util.spec_from_file_location("apply_task_contacts", SCRIPT_PATH)
assert SPEC and SPEC.loader
APPLY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APPLY)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def table_exists(path: Path, table: str) -> bool:
    with sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True) as connection:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone() is not None


def core_counts(path: Path) -> dict[str, int]:
    with sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True) as connection:
        return {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in ("tasks", "aliases", "event_logs")
        }


@pytest.fixture
def cli_project(tmp_path, monkeypatch, synthetic_contact_dataset):
    project = tmp_path / "project"
    db = project / "data" / "health_search.db"
    backup = (
        project
        / "data"
        / "backups"
        / "health_search.pre-task-contacts-20260828_114610-5cbd33041a23.db"
    )
    xlsx = (
        project
        / "data"
        / "source"
        / "동탄구보건소_검색업무별_공식연락처_확정대조_2026-08-28.xlsx"
    )
    schema = project / "sql" / "task_contacts_schema.sql"
    tasks = project / "data" / "tasks.json"
    for path in (db, backup, xlsx, schema, tasks):
        path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(synthetic_contact_dataset.backup, backup)
    shutil.copy2(synthetic_contact_dataset.workbook, xlsx)
    shutil.copy2(SOURCE_SCHEMA, schema)
    shutil.copy2(synthetic_contact_dataset.tasks, tasks)
    APPLY.MIGRATION.backup_database(backup, db)

    monkeypatch.setattr(APPLY, "ROOT", project)
    monkeypatch.setattr(APPLY, "DEFAULT_DB", db)
    monkeypatch.setattr(APPLY, "DEFAULT_XLSX", xlsx)
    monkeypatch.setattr(APPLY, "DEFAULT_SCHEMA", schema)
    monkeypatch.setattr(APPLY, "DEFAULT_BACKUP", backup)
    monkeypatch.setattr(APPLY, "DEFAULT_TASKS", tasks)
    monkeypatch.setattr(APPLY, "APPROVED_DB_SHA256", file_sha256(db))
    monkeypatch.setattr(APPLY, "APPROVED_XLSX_SHA256", file_sha256(xlsx))
    monkeypatch.setattr(APPLY, "APPROVED_BACKUP_SHA256", file_sha256(backup))
    monkeypatch.setattr(APPLY, "_port_5000_open", lambda: False)
    monkeypatch.setattr(APPLY, "_project_python_processes", lambda: [])

    original_load_importer = APPLY.MIGRATION.load_importer

    def load_synthetic_importer():
        importer = original_load_importer()
        importer.EXPECTED_WORKBOOK_SHA256 = file_sha256(xlsx)
        return importer

    monkeypatch.setattr(APPLY.MIGRATION, "load_importer", load_synthetic_importer)
    return {
        "root": project,
        "db": db,
        "backup": backup,
        "xlsx": xlsx,
        "schema": schema,
        "tasks": tasks,
    }


def apply_args(project: dict[str, Path]) -> list[str]:
    return [
        "--apply",
        "--confirm",
        APPLY.CONFIRM_TEXT,
        "--db",
        str(project["db"]),
        "--xlsx",
        str(project["xlsx"]),
        "--schema",
        str(project["schema"]),
        "--backup",
        str(project["backup"]),
        "--expected-db-sha256",
        APPLY.APPROVED_DB_SHA256,
        "--expected-xlsx-sha256",
        APPLY.APPROVED_XLSX_SHA256,
        "--expected-backup-sha256",
        APPLY.APPROVED_BACKUP_SHA256,
    ]


def assert_pristine(path: Path) -> None:
    assert not table_exists(path, "task_contacts")
    assert core_counts(path) == {"tasks": 63, "aliases": 316, "event_logs": 114}


def test_no_arguments_prints_usage_and_writes_nothing(cli_project, capsys):
    before = file_sha256(cli_project["db"])
    assert APPLY.main([]) == 0
    assert "usage:" in capsys.readouterr().out
    assert file_sha256(cli_project["db"]) == before
    assert_pristine(cli_project["db"])


def test_dry_run_is_read_only(cli_project, capsys):
    before = file_sha256(cli_project["db"])
    assert APPLY.main(["--dry-run"]) == 0
    output = capsys.readouterr().out
    assert '"mode": "dry-run"' in output
    assert '"database_writes": 0' in output
    assert file_sha256(cli_project["db"]) == before
    assert_pristine(cli_project["db"])


def test_apply_requires_every_explicit_argument(cli_project, capsys):
    before = file_sha256(cli_project["db"])
    assert APPLY.main(["--apply"]) == 2
    assert "필수 인수 누락" in capsys.readouterr().err
    assert file_sha256(cli_project["db"]) == before


def test_apply_rejects_wrong_confirmation(cli_project, capsys):
    args = apply_args(cli_project)
    args[args.index(APPLY.CONFIRM_TEXT)] = "WRONG_CONFIRMATION"
    assert APPLY.main(args) == 2
    assert "확인 문자열" in capsys.readouterr().err
    assert_pristine(cli_project["db"])


def test_apply_rejects_open_port_5000(cli_project, monkeypatch, capsys):
    monkeypatch.setattr(APPLY, "_port_5000_open", lambda: True)

    assert APPLY.main(apply_args(cli_project)) == 2
    assert "5000" in capsys.readouterr().err
    assert_pristine(cli_project["db"])


def test_apply_rejects_project_python_process(cli_project, monkeypatch, capsys):
    monkeypatch.setattr(
        APPLY,
        "_project_python_processes",
        lambda: [{"pid": 1234, "command_line": "python app.py"}],
    )

    assert APPLY.main(apply_args(cli_project)) == 2
    assert "Python" in capsys.readouterr().err
    assert_pristine(cli_project["db"])


@pytest.mark.parametrize(
    ("key", "option"),
    (("db", "--expected-db-sha256"), ("xlsx", "--expected-xlsx-sha256"), ("backup", "--expected-backup-sha256")),
)
def test_apply_rejects_changed_file_hash(cli_project, capsys, key, option):
    path = cli_project[key]
    with path.open("ab") as stream:
        stream.write(b"changed-after-approval")
    args = apply_args(cli_project)
    assert APPLY.main(args) == 2
    assert "SHA-256 불일치" in capsys.readouterr().err
    if key != "db":
        assert_pristine(cli_project["db"])


def test_apply_rejects_wrong_approved_hash_argument(cli_project, capsys):
    args = apply_args(cli_project)
    index = args.index("--expected-db-sha256") + 1
    args[index] = "0" * 64
    assert APPLY.main(args) == 2
    assert "승인 SHA-256" in capsys.readouterr().err
    assert_pristine(cli_project["db"])


def test_apply_rejects_path_outside_the_pinned_project(cli_project, tmp_path, capsys):
    alternate = tmp_path / "alternate.db"
    shutil.copy2(cli_project["db"], alternate)
    args = apply_args(cli_project)
    args[args.index("--db") + 1] = str(alternate)
    assert APPLY.main(args) == 2
    assert "고정된 프로젝트 파일" in capsys.readouterr().err
    assert_pristine(cli_project["db"])


@pytest.mark.parametrize("table", ("tasks", "aliases", "event_logs"))
def test_apply_rejects_changed_core_counts(cli_project, capsys, table):
    with sqlite3.connect(cli_project["db"]) as connection:
        connection.execute(f'DELETE FROM "{table}" WHERE rowid = (SELECT MAX(rowid) FROM "{table}")')
    changed_hash = file_sha256(cli_project["db"])
    APPLY.APPROVED_DB_SHA256 = changed_hash
    args = apply_args(cli_project)
    assert APPLY.main(args) == 2
    assert "기준 테이블 수량 불일치" in capsys.readouterr().err
    assert not table_exists(cli_project["db"], "task_contacts")


def test_apply_rejects_existing_task_contacts_table(cli_project, capsys):
    with sqlite3.connect(cli_project["db"]) as connection:
        connection.execute("CREATE TABLE task_contacts(id INTEGER PRIMARY KEY)")
    APPLY.APPROVED_DB_SHA256 = file_sha256(cli_project["db"])
    assert APPLY.main(apply_args(cli_project)) == 2
    assert "이미 존재" in capsys.readouterr().err


def test_full_production_cli_path_applies_only_to_temporary_db(cli_project, capsys):
    assert APPLY.main(apply_args(cli_project)) == 0
    capsys.readouterr()
    with sqlite3.connect(cli_project["db"]) as connection:
        validation = APPLY.MIGRATION.validate_database(connection)
        assert validation["total_contact_rows"] == 93
        assert validation["staging_task_count"] == 51
        assert validation["primary_contact_rows"] == 45
        assert validation["duplicate_count"] == 0
        assert validation["primary_duplicate_count"] == 0
        assert validation["orphan_task_id_count"] == 0
        assert validation["foreign_key_check"] == []
        assert validation["integrity_check"] == ["ok"]
        assert APPLY.validate_core_contacts(connection)
        held = connection.execute(
            f"SELECT COUNT(*) FROM task_contacts WHERE active = 1 AND task_id IN "
            f"({','.join('?' for _ in APPLY.HELD_TASK_IDS)})",
            sorted(APPLY.HELD_TASK_IDS),
        ).fetchone()[0]
        assert held == 0
    assert core_counts(cli_project["db"]) == {"tasks": 63, "aliases": 316, "event_logs": 114}


def test_reapplication_is_refused(cli_project, capsys):
    args = apply_args(cli_project)
    assert APPLY.main(args) == 0
    capsys.readouterr()
    assert APPLY.main(args) == 2
    assert "SHA-256 불일치" in capsys.readouterr().err
    with sqlite3.connect(cli_project["db"]) as connection:
        assert connection.execute("SELECT COUNT(*) FROM task_contacts").fetchone()[0] == 93


def test_failure_after_schema_creation_rolls_back_table(cli_project, monkeypatch, capsys):
    def fail_before_rows(connection, rows, importer):
        raise RuntimeError("injected after schema")

    monkeypatch.setattr(APPLY.MIGRATION, "apply_contact_rows", fail_before_rows)
    assert APPLY.main(apply_args(cli_project)) == 2
    assert "injected after schema" in capsys.readouterr().err
    assert_pristine(cli_project["db"])


def test_failure_after_partial_insert_rolls_back_table_and_rows(cli_project, monkeypatch, capsys):
    def fail_after_one_row(connection, rows, importer):
        APPLY.MIGRATION.validate_contact_rows(rows, importer)
        APPLY.MIGRATION.insert_row(connection, rows[0])
        raise RuntimeError("injected after one row")

    monkeypatch.setattr(APPLY.MIGRATION, "apply_contact_rows", fail_after_one_row)
    assert APPLY.main(apply_args(cli_project)) == 2
    assert "injected after one row" in capsys.readouterr().err
    assert_pristine(cli_project["db"])


def test_precommit_failure_rolls_back_schema_and_all_rows(cli_project, monkeypatch, capsys):
    def fail_precommit(connection, before_core):
        assert connection.execute("SELECT COUNT(*) FROM task_contacts").fetchone()[0] == 93
        raise RuntimeError("injected before commit")

    monkeypatch.setattr(APPLY, "validate_precommit", fail_precommit)
    assert APPLY.main(apply_args(cli_project)) == 2
    assert "injected before commit" in capsys.readouterr().err
    assert_pristine(cli_project["db"])


def test_synthetic_inputs_remain_at_their_fixture_baseline(synthetic_contact_dataset):
    assert file_sha256(synthetic_contact_dataset.db) == synthetic_contact_dataset.db_sha256
    assert file_sha256(synthetic_contact_dataset.backup) == synthetic_contact_dataset.backup_sha256
    assert file_sha256(synthetic_contact_dataset.workbook) == (
        synthetic_contact_dataset.workbook_sha256
    )
    assert core_counts(synthetic_contact_dataset.db) == {
        "tasks": 63,
        "aliases": 316,
        "event_logs": 114,
    }
    assert not table_exists(synthetic_contact_dataset.db, "task_contacts")
