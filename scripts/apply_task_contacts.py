"""Safely apply the approved task_contacts migration to the pinned database.

Running without arguments prints usage.  Any invocation other than an explicit,
fully confirmed ``--apply`` is read-only.  The schema and contact rows are
committed together in one caller-owned SQLite transaction.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import sqlite3
import stat
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "health_search.db"
DEFAULT_XLSX = (
    ROOT
    / "data"
    / "source"
    / "동탄구보건소_검색업무별_공식연락처_확정대조_2026-08-28.xlsx"
)
DEFAULT_SCHEMA = ROOT / "sql" / "task_contacts_schema.sql"
DEFAULT_BACKUP = (
    ROOT
    / "data"
    / "backups"
    / "health_search.pre-task-contacts-20260828_114610-5cbd33041a23.db"
)
DEFAULT_TASKS = ROOT / "data" / "tasks.json"
MIGRATION_PATH = Path(__file__).with_name("validate_task_contacts_migration.py")

APPROVED_DB_SHA256 = "5cbd33041a236cc41851a8e54a694b2679215b9ab93c16e0f072d0e285ed4583"
APPROVED_XLSX_SHA256 = "95862ee7a5bfdf7e349208ae6eeafe19353a1ff8bf97f975d9fd18937a7a253e"
APPROVED_BACKUP_SHA256 = "47fc64db7080566b497706fe920f21fdc1c10de3a60dc4efb525b9cb6905c0cb"
CONFIRM_TEXT = "APPLY_TASK_CONTACTS_93"

EXPECTED_COUNTS = {"tasks": 63, "aliases": 316, "event_logs": 114}
EXPECTED_CONTACT_ROWS = 93
EXPECTED_CONTACT_TASKS = 51
EXPECTED_PRIMARY_ROWS = 45
EXPECTED_MULTIPLE_STATUS_TASKS = 9
EXPECTED_CONDITIONAL_TASKS = 11
HELD_TASK_IDS = {
    "H004",
    "F105",
    "F109",
    "F111",
    "F202",
    "F203",
    "F205",
    "F206",
    "F301",
    "F302",
    "F303",
    "F304",
}
REQUIRED_APPLY_OPTIONS = {
    "--confirm",
    "--db",
    "--xlsx",
    "--schema",
    "--backup",
    "--expected-db-sha256",
    "--expected-xlsx-sha256",
    "--expected-backup-sha256",
}


class ApplySafetyError(RuntimeError):
    """Raised before commit when an approved apply invariant is not satisfied."""


def load_migration_module():
    spec = importlib.util.spec_from_file_location("task_contacts_migration", MIGRATION_PATH)
    if not spec or not spec.loader:
        raise ApplySafetyError(f"migration 모듈을 불러올 수 없습니다: {MIGRATION_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = load_migration_module()


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=True)


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def validate_exact_path(name: str, supplied: Path, expected: Path) -> Path:
    try:
        supplied_resolved = _resolved(supplied)
        expected_resolved = _resolved(expected)
        root_resolved = _resolved(ROOT)
    except OSError as error:
        raise ApplySafetyError(f"{name} 경로를 확인할 수 없습니다: {error}") from error
    if supplied.is_symlink() or _is_reparse_point(supplied):
        raise ApplySafetyError(f"{name}에 심볼릭 링크/reparse point를 사용할 수 없습니다.")
    if supplied_resolved != expected_resolved:
        raise ApplySafetyError(
            f"{name}은 고정된 프로젝트 파일이어야 합니다: {expected_resolved}"
        )
    try:
        supplied_resolved.relative_to(root_resolved)
    except ValueError as error:
        raise ApplySafetyError(f"{name}이 프로젝트 밖을 가리킵니다.") from error
    return supplied_resolved


def validate_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "db": validate_exact_path("DB", args.db, DEFAULT_DB),
        "xlsx": validate_exact_path("XLSX", args.xlsx, DEFAULT_XLSX),
        "schema": validate_exact_path("schema", args.schema, DEFAULT_SCHEMA),
        "backup": validate_exact_path("backup", args.backup, DEFAULT_BACKUP),
        "tasks": validate_exact_path("tasks", DEFAULT_TASKS, DEFAULT_TASKS),
    }


def _option_present(argv: list[str], option: str) -> bool:
    return option in argv or any(token.startswith(f"{option}=") for token in argv)


def require_explicit_apply_args(argv: list[str], args: argparse.Namespace) -> None:
    missing = sorted(option for option in REQUIRED_APPLY_OPTIONS if not _option_present(argv, option))
    if missing:
        raise ApplySafetyError(f"--apply 필수 인수 누락: {', '.join(missing)}")
    if args.confirm != CONFIRM_TEXT:
        raise ApplySafetyError("운영 적용 확인 문자열이 일치하지 않습니다.")
    approved = {
        "DB": (args.expected_db_sha256, APPROVED_DB_SHA256),
        "XLSX": (args.expected_xlsx_sha256, APPROVED_XLSX_SHA256),
        "backup": (args.expected_backup_sha256, APPROVED_BACKUP_SHA256),
    }
    for name, (supplied, expected) in approved.items():
        if str(supplied).casefold() != expected:
            raise ApplySafetyError(f"{name} 승인 SHA-256 인수가 고정값과 다릅니다.")


def _port_5000_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(0.25)
        return client.connect_ex(("127.0.0.1", 5000)) == 0


def _project_python_processes() -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    root_literal = str(ROOT.resolve()).replace("'", "''")
    script = (
        "$items = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Name -match '^python(w)?\\.exe$' -and "
        f"$_.CommandLine -like '*{root_literal}*' }} | "
        "Select-Object ProcessId,CommandLine; $items | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ApplySafetyError("프로젝트 Python 프로세스 상태를 해석할 수 없습니다.") from error
    items = payload if isinstance(payload, list) else [payload]
    excluded = {os.getpid(), os.getppid()}
    return [item for item in items if int(item.get("ProcessId", -1)) not in excluded]


def assert_server_stopped() -> None:
    port_open = _port_5000_open()
    processes = _project_python_processes()
    if port_open or processes:
        details = {
            "port_5000_open": port_open,
            "project_python_processes": processes,
        }
        raise ApplySafetyError(
            "Flask/포트 5000 또는 프로젝트 Python 프로세스가 실행 중입니다: "
            + json.dumps(details, ensure_ascii=False)
        )


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone() is not None


def inspect_base_database(path: Path, *, require_contacts_absent: bool) -> dict[str, Any]:
    with closing(MIGRATION.readonly_connection(path)) as connection:
        counts = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in EXPECTED_COUNTS
        }
        if counts != EXPECTED_COUNTS:
            raise ApplySafetyError(f"기준 테이블 수량 불일치: {counts}")
        contact_exists = _table_exists(connection, "task_contacts")
        if require_contacts_absent and contact_exists:
            raise ApplySafetyError("task_contacts 테이블이 이미 존재하여 재적용을 거부합니다.")
        integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        foreign_keys = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
        task_ids = {
            str(row[0]) for row in connection.execute("SELECT id FROM tasks").fetchall()
        }
        if integrity != ["ok"] or foreign_keys:
            raise ApplySafetyError(
                f"DB 무결성 검사 실패: integrity={integrity}, foreign_keys={foreign_keys}"
            )
        return {
            "counts": counts,
            "task_contacts_exists": contact_exists,
            "integrity_check": integrity,
            "foreign_key_check": foreign_keys,
            "task_ids": task_ids,
            "core_snapshot": MIGRATION.core_table_snapshot(connection),
        }


def preflight(args: argparse.Namespace, paths: dict[str, Path]) -> dict[str, Any]:
    actual_hashes = {
        "db": MIGRATION.sha256_file(paths["db"]),
        "xlsx": MIGRATION.sha256_file(paths["xlsx"]),
        "backup": MIGRATION.sha256_file(paths["backup"]),
    }
    expected_hashes = {
        "db": str(args.expected_db_sha256).casefold(),
        "xlsx": str(args.expected_xlsx_sha256).casefold(),
        "backup": str(args.expected_backup_sha256).casefold(),
    }
    for name in actual_hashes:
        if actual_hashes[name] != expected_hashes[name]:
            raise ApplySafetyError(
                f"{name} SHA-256 불일치: expected={expected_hashes[name]}, "
                f"actual={actual_hashes[name]}"
            )

    database = inspect_base_database(paths["db"], require_contacts_absent=True)
    backup = inspect_base_database(paths["backup"], require_contacts_absent=True)
    importer = MIGRATION.load_importer()
    if importer.EXPECTED_WORKBOOK_SHA256 != APPROVED_XLSX_SHA256:
        raise ApplySafetyError("importer의 고정 XLSX SHA-256이 승인값과 다릅니다.")
    payload, import_report = importer.run_import(
        paths["xlsx"], paths["tasks"], paths["db"], args.expected_xlsx_sha256
    )
    if not import_report["validation_passed"]:
        raise ApplySafetyError(f"XLSX importer 검증 실패: {import_report['errors']}")
    rows = MIGRATION.build_contact_rows(payload, importer)

    excel_ids = {str(item["task_id"]) for item in payload["matches"]}
    if excel_ids != database["task_ids"] or len(excel_ids) != 63:
        raise ApplySafetyError("XLSX 업무 ID와 DB 업무 ID가 완전히 일치하지 않습니다.")
    held_ids = {
        str(item["task_id"])
        for item in payload["matches"]
        if item["match_status"] in importer.HOLD_STATUSES
    }
    if held_ids != HELD_TASK_IDS:
        raise ApplySafetyError(
            f"보류 업무 집합 불일치: {sorted(held_ids)}"
        )
    eligible_ids = {row["task_id"] for row in rows}
    if eligible_ids & HELD_TASK_IDS:
        raise ApplySafetyError("보류 업무가 활성 연락처 staging에 포함되었습니다.")
    return {
        "hashes": actual_hashes,
        "database": database,
        "backup": backup,
        "importer": importer,
        "payload": payload,
        "rows": rows,
        "held_ids": held_ids,
        "eligible_ids": eligible_ids,
        "import_report": import_report,
    }


def _assert_equal(name: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise ApplySafetyError(f"{name} 불일치: expected={expected}, actual={actual}")


def validate_core_contacts(connection: sqlite3.Connection) -> dict[str, Any]:
    contacts = MIGRATION.fetch_contacts_by_task(connection)
    expected_single = [{"phone": "031-5189-4364", "is_primary": 1}]
    for task_id in ("A011", "F101"):
        actual = [
            {"phone": row["phone"], "is_primary": row["is_primary"]}
            for row in contacts.get(task_id, [])
        ]
        _assert_equal(f"{task_id} 연락처", actual, expected_single)
    expected_a012 = {
        ("031-5189-4364", "대표전화", 1),
        ("031-5189-4344", "흉부 X선", 0),
        ("031-5189-4369", "검체검사", 0),
        ("031-5189-4368", "진단검사실", 0),
        ("031-5189-4377", "민원접수", 0),
    }
    actual_a012 = {
        (row["phone"], row["label"], row["is_primary"])
        for row in contacts.get("A012", [])
    }
    _assert_equal("A012 연락처", actual_a012, expected_a012)
    excluded = [
        row
        for task_id in ("A011", "A012", "F101")
        for row in contacts.get(task_id, [])
        if row["phone"] == "031-5189-4354"
    ]
    _assert_equal("보호 업무의 서남부권 결핵 번호", excluded, [])
    return {task_id: contacts.get(task_id, []) for task_id in ("A011", "A012", "F101")}


def validate_precommit(
    connection: sqlite3.Connection,
    before_core: dict[str, Any],
) -> dict[str, Any]:
    validation = MIGRATION.validate_database(connection)
    expected = {
        "total_contact_rows": EXPECTED_CONTACT_ROWS,
        "active_contact_rows": EXPECTED_CONTACT_ROWS,
        "staging_task_count": EXPECTED_CONTACT_TASKS,
        "primary_contact_rows": EXPECTED_PRIMARY_ROWS,
        "duplicate_count": 0,
        "primary_duplicate_count": 0,
        "orphan_task_id_count": 0,
        "foreign_key_check": [],
        "integrity_check": ["ok"],
    }
    for name, value in expected.items():
        _assert_equal(name, validation[name], value)

    counts = {
        table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        for table in EXPECTED_COUNTS
    }
    _assert_equal("기준 테이블 수량", counts, EXPECTED_COUNTS)
    _assert_equal("기준 테이블 논리 내용", MIGRATION.core_table_snapshot(connection), before_core)
    held_count = connection.execute(
        f"SELECT COUNT(*) FROM task_contacts WHERE active = 1 AND task_id IN "
        f"({','.join('?' for _ in HELD_TASK_IDS)})",
        sorted(HELD_TASK_IDS),
    ).fetchone()[0]
    _assert_equal("보류 업무 활성 연락처", held_count, 0)
    status_counts = {
        status: connection.execute(
            "SELECT COUNT(DISTINCT task_id) FROM task_contacts "
            "WHERE active = 1 AND match_status = ?",
            (status,),
        ).fetchone()[0]
        for status in ("confirmed_multiple", "conditional")
    }
    _assert_equal(
        "confirmed_multiple 업무 수",
        status_counts["confirmed_multiple"],
        EXPECTED_MULTIPLE_STATUS_TASKS,
    )
    _assert_equal(
        "conditional 업무 수",
        status_counts["conditional"],
        EXPECTED_CONDITIONAL_TASKS,
    )
    core = validate_core_contacts(connection)
    return {
        "validation": validation,
        "counts": counts,
        "status_counts": status_counts,
        "held_active_rows": held_count,
        "core_contacts": core,
        "contact_logical_sha256": MIGRATION.contact_snapshot(connection)["sha256"],
    }


def apply_transaction(paths: dict[str, Path], prepared: dict[str, Any]) -> dict[str, Any]:
    connection = sqlite3.connect(paths["db"], isolation_level=None)
    connection.row_factory = sqlite3.Row
    committed = False
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        _assert_equal("PRAGMA foreign_keys", connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        before_core = MIGRATION.core_table_snapshot(connection)
        connection.execute("BEGIN IMMEDIATE")
        MIGRATION.migrate_schema(connection, paths["schema"])
        apply_result = MIGRATION.apply_contact_rows(
            connection, prepared["rows"], prepared["importer"]
        )
        validation = validate_precommit(connection, before_core)
        connection.commit()
        committed = True
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()
    post = inspect_base_database(paths["db"], require_contacts_absent=False)
    with closing(MIGRATION.readonly_connection(paths["db"])) as read_connection:
        post_validation = validate_precommit(read_connection, prepared["database"]["core_snapshot"])
    return {
        "committed": committed,
        "apply_result": apply_result,
        "precommit": validation,
        "postcommit": post_validation,
        "post_db_sha256": MIGRATION.sha256_file(paths["db"]),
        "post_database": {
            "counts": post["counts"],
            "task_contacts_exists": post["task_contacts_exists"],
            "integrity_check": post["integrity_check"],
            "foreign_key_check": post["foreign_key_check"],
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="읽기 전용 사전검사만 수행합니다.")
    mode.add_argument("--apply", action="store_true", help="모든 안전조건이 맞을 때 단일 transaction으로 적용합니다.")
    parser.add_argument("--confirm")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--expected-db-sha256", default=APPROVED_DB_SHA256)
    parser.add_argument("--expected-xlsx-sha256", default=APPROVED_XLSX_SHA256)
    parser.add_argument("--expected-backup-sha256", default=APPROVED_BACKUP_SHA256)
    return parser


def _public_report(paths: dict[str, Path], prepared: dict[str, Any], mode: str) -> dict[str, Any]:
    rows = prepared["rows"]
    return {
        "mode": mode,
        "paths": {name: str(path) for name, path in paths.items() if name != "tasks"},
        "hashes": prepared["hashes"],
        "staging_task_count": len(prepared["eligible_ids"]),
        "contact_row_count": len(rows),
        "primary_row_count": sum(int(row["is_primary"]) for row in rows),
        "held_task_count": len(prepared["held_ids"]),
        "database_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not raw_argv:
        parser.print_usage()
        return 0
    args = parser.parse_args(raw_argv)
    mode = "apply" if args.apply else "dry-run"
    planned = {
        "mode": mode,
        "db": str(args.db),
        "xlsx": str(args.xlsx),
        "schema": str(args.schema),
        "backup": str(args.backup),
    }
    print(json.dumps({"planned": planned}, ensure_ascii=False))
    try:
        if args.apply:
            require_explicit_apply_args(raw_argv, args)
        paths = validate_paths(args)
        assert_server_stopped()
        prepared = preflight(args, paths)
        report = _public_report(paths, prepared, mode)
        if args.apply:
            result = apply_transaction(paths, prepared)
            report.update(result)
            report["database_writes"] = result["apply_result"]["inserted"]
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0
    except Exception as error:
        print(f"적용 거부: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
