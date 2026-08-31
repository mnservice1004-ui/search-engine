"""Exercise the task_contacts migration on a temporary SQLite backup only.

This command has no mode that writes to ``data/health_search.db``.  It opens
the source database read-only, copies it with SQLite's backup API, and performs
all DDL/DML and failure-injection tests on the temporary copy.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sqlite3
import sys
import tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "health_search.db"
DEFAULT_WORKBOOK = (
    ROOT
    / "data"
    / "source"
    / "동탄구보건소_검색업무별_공식연락처_확정대조_2026-08-28.xlsx"
)
DEFAULT_TASKS = ROOT / "data" / "tasks.json"
DEFAULT_SCHEMA = ROOT / "sql" / "task_contacts_schema.sql"
CONTACT_MATCHES_PATH = ROOT / "data" / "contact_matches.json"
IMPORTER_PATH = Path(__file__).with_name("import_confirmed_contacts.py")

EXPECTED_LIVE_COUNTS = {"tasks": 63, "aliases": 316, "event_logs": 114}
EXPECTED_STAGING_TASKS = 51
EXPECTED_CONTACT_ROWS = 93
EXPECTED_PRIMARY_ROWS = 45
EXPECTED_CONFIRMED_MULTIPLE_TASKS = 9
EXPECTED_CONDITIONAL_TASKS = 11
EXPECTED_HELD_TASKS = 12
ELIGIBLE_STATUSES = {"confirmed", "confirmed_multiple", "conditional"}
PROTECTED_TASK_IDS = {"A011", "A012", "F101"}
EXCLUDED_PROTECTED_PHONE = "031-5189-4354"
PROVENANCE_NOTES = {"기존 근거"}


class TrialValidationError(RuntimeError):
    """Raised when staging or the temporary migration violates a contract."""


def load_importer():
    spec = importlib.util.spec_from_file_location("confirmed_contact_importer", IMPORTER_PATH)
    if not spec or not spec.loader:
        raise TrialValidationError(f"importer를 불러올 수 없습니다: {IMPORTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def readonly_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def database_counts(path: Path) -> dict[str, int]:
    with closing(readonly_connection(path)) as connection:
        return {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in ("tasks", "aliases", "event_logs")
        }


def backup_database(source_path: Path, destination_path: Path) -> None:
    if source_path.resolve() == destination_path.resolve():
        raise TrialValidationError("운영 DB를 backup 대상 경로로 사용할 수 없습니다.")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(readonly_connection(source_path)) as source:
        with closing(sqlite3.connect(destination_path)) as destination:
            source.backup(destination)


def split_sql_statements(sql_text: str) -> list[str]:
    statements: list[str] = []
    buffer = ""
    for line in sql_text.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                statements.append(statement)
            buffer = ""
    if buffer.strip():
        raise TrialValidationError("완결되지 않은 SQL 문장이 있습니다.")
    return statements


def migrate_schema(connection: sqlite3.Connection, schema_path: Path = DEFAULT_SCHEMA) -> None:
    """Apply and validate the schema inside a caller-owned transaction."""

    if not connection.in_transaction:
        raise TrialValidationError("스키마 적용에는 외부 transaction이 필요합니다.")
    statements = split_sql_statements(schema_path.read_text(encoding="utf-8"))
    for statement in statements:
        connection.execute(statement)
    validate_schema_contract(connection)


def validate_schema_contract(connection: sqlite3.Connection) -> None:
    column_rows = connection.execute("PRAGMA table_info(task_contacts)").fetchall()
    columns = {row[1]: row for row in column_rows}
    required_columns = {
        "id",
        "task_id",
        "phone",
        "display_phone",
        "label",
        "note",
        "contact_role",
        "condition_text",
        "is_primary",
        "source_url",
        "source_urls_json",
        "source_sheet",
        "source_row",
        "verified_at",
        "match_status",
        "active",
    }
    missing_columns = sorted(required_columns - set(columns))
    if missing_columns:
        raise TrialValidationError(
            f"task_contacts 필수 열 누락: {', '.join(missing_columns)}"
        )

    required_not_null = required_columns - {"id", "note", "contact_role", "condition_text"}
    nullable_required = sorted(
        column for column in required_not_null if int(columns[column][3]) != 1
    )
    if nullable_required:
        raise TrialValidationError(
            f"task_contacts NOT NULL 제약 누락: {', '.join(nullable_required)}"
        )

    foreign_keys = connection.execute("PRAGMA foreign_key_list(task_contacts)").fetchall()
    if not any(
        row[2] == "tasks"
        and row[3] == "task_id"
        and row[4] == "id"
        and str(row[6]).upper() == "CASCADE"
        for row in foreign_keys
    ):
        raise TrialValidationError("task_contacts.task_id 외래키 또는 CASCADE 제약이 없습니다.")

    index_rows = connection.execute("PRAGMA index_list(task_contacts)").fetchall()
    natural_key_found = False
    primary_index_found = False
    for index_row in index_rows:
        index_name = index_row[1]
        unique = int(index_row[2]) == 1
        partial = int(index_row[4]) == 1
        index_columns = [
            row[2]
            for row in connection.execute(
                f'PRAGMA index_info("{index_name.replace(chr(34), chr(34) * 2)}")'
            ).fetchall()
        ]
        if unique and not partial and index_columns == ["task_id", "phone", "label"]:
            natural_key_found = True
        if index_name == "idx_task_contacts_one_active_primary":
            sql_row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
                (index_name,),
            ).fetchone()
            normalized_sql = " ".join(str(sql_row[0] if sql_row else "").lower().split())
            where_matches = re.search(
                r"where\s+is_primary\s*=\s*1\s+and\s+active\s*=\s*1\s*$",
                normalized_sql,
            )
            primary_index_found = bool(
                unique and partial and index_columns == ["task_id"] and where_matches
            )
    if not natural_key_found:
        raise TrialValidationError("task_contacts 업무/전화번호/용도 UNIQUE 제약이 없습니다.")
    if not primary_index_found:
        raise TrialValidationError("task_contacts 활성 primary partial UNIQUE 제약이 잘못되었습니다.")


def normalize_label(contact: dict[str, Any]) -> str:
    role = str(contact.get("role") or "").strip()
    condition = str(contact.get("condition_text") or "").strip()
    if contact.get("is_primary"):
        return "대표전화"
    return condition or role or "추가 연락처"


def is_official_hscity_url(value: Any) -> bool:
    parsed = urlparse(str(value or "").strip())
    hostname = (parsed.hostname or "").casefold()
    return bool(
        parsed.scheme.casefold() == "https"
        and parsed.username is None
        and parsed.password is None
        and (hostname == "hscity.go.kr" or hostname.endswith(".hscity.go.kr"))
    )


def build_contact_rows(
    payload: dict[str, Any],
    importer: Any,
    *,
    expected_workbook_sha256: str | None = None,
) -> list[dict[str, Any]]:
    source = payload.get("source") or {}
    approved_workbook_sha256 = expected_workbook_sha256 or importer.EXPECTED_WORKBOOK_SHA256
    if source.get("sha256") != approved_workbook_sha256:
        raise TrialValidationError("staging payload의 XLSX SHA-256이 고정값과 다릅니다.")
    source_sheet = str(source.get("sheet") or "").strip()
    if source_sheet != importer.FINAL_SHEET:
        raise TrialValidationError("staging payload의 원본 시트가 예상값과 다릅니다.")

    rows: list[dict[str, Any]] = []
    for match in payload.get("matches", []):
        status = str(match.get("match_status") or "").strip()
        if status not in ELIGIBLE_STATUSES:
            continue
        source_urls = list(match.get("source_urls") or [])
        if not source_urls:
            raise TrialValidationError(f"{match.get('task_id')}: 공식 출처 URL이 없습니다.")
        evidence = match.get("evidence") or {}
        for contact in match.get("contacts") or []:
            phone = str(contact.get("phone") or "").strip()
            note = str(contact.get("note") or "").strip() or None
            condition_text = str(contact.get("condition_text") or "").strip() or None
            if note in PROVENANCE_NOTES and condition_text == note:
                condition_text = str(match.get("condition_text") or "").strip() or None
            normalized_contact = dict(contact)
            normalized_contact["condition_text"] = condition_text
            rows.append(
                {
                    "task_id": str(match.get("task_id") or "").strip(),
                    "phone": phone,
                    "display_phone": phone,
                    "label": normalize_label(normalized_contact),
                    "note": note,
                    "contact_role": contact.get("role"),
                    "condition_text": condition_text,
                    "is_primary": 1 if contact.get("is_primary") else 0,
                    "source_url": source_urls[0],
                    "source_urls_json": json.dumps(
                        source_urls, ensure_ascii=False, separators=(",", ":")
                    ),
                    "source_sheet": source_sheet,
                    "source_row": evidence.get("workbook_row"),
                    "verified_at": match.get("verified_at"),
                    "match_status": status,
                    "active": 1,
                }
            )
    rows.sort(
        key=lambda row: (
            row["task_id"],
            -row["is_primary"],
            row["label"],
            row["phone"],
        )
    )
    validate_contact_rows(rows, importer)
    return rows


def validate_contact_rows(rows: list[dict[str, Any]], importer: Any) -> None:
    errors: list[str] = []
    task_ids = {row["task_id"] for row in rows}
    natural_keys = [(row["task_id"], row["phone"], row["label"]) for row in rows]
    duplicate_keys = sorted(key for key, count in Counter(natural_keys).items() if count > 1)
    if duplicate_keys:
        errors.append(f"중복 task/phone/label: {duplicate_keys}")

    primary_counts = Counter(row["task_id"] for row in rows if row["is_primary"] == 1)
    duplicate_primary = sorted(task_id for task_id, count in primary_counts.items() if count > 1)
    if duplicate_primary:
        errors.append(f"업무별 primary 중복: {', '.join(duplicate_primary)}")

    for row in rows:
        if row["match_status"] not in ELIGIBLE_STATUSES:
            errors.append(f"보류 상태가 활성 row에 포함됨: {row['task_id']}")
        if not importer.PHONE_CANONICAL_PATTERN.fullmatch(row["phone"]):
            errors.append(f"잘못된 전화번호: {row['task_id']} {row['phone']}")
        if row["display_phone"] != row["phone"]:
            errors.append(f"display_phone 불일치: {row['task_id']} {row['phone']}")
        if not str(row["label"]).strip():
            errors.append(f"빈 연락처 용도: {row['task_id']} {row['phone']}")
        if not is_official_hscity_url(row["source_url"]):
            errors.append(f"비공식 URL: {row['task_id']} {row['source_url']}")
        try:
            source_urls = json.loads(str(row["source_urls_json"]))
        except json.JSONDecodeError:
            source_urls = None
        if not isinstance(source_urls, list) or not source_urls:
            errors.append(f"공식 URL 목록 오류: {row['task_id']}")
        elif row["source_url"] != source_urls[0]:
            errors.append(f"대표 출처 URL 불일치: {row['task_id']}")
        else:
            for source_url in source_urls:
                if not is_official_hscity_url(source_url):
                    errors.append(f"비공식 URL 목록 항목: {row['task_id']} {source_url}")
        if row["source_sheet"] != importer.FINAL_SHEET:
            errors.append(f"원본 시트 불일치: {row['task_id']}")
        if not isinstance(row["source_row"], int) or row["source_row"] < 2:
            errors.append(f"원본 행 불일치: {row['task_id']} {row['source_row']}")
        if not str(row["verified_at"] or "").strip():
            errors.append(f"확인일 누락: {row['task_id']}")

    status_task_counts = Counter()
    for status in ELIGIBLE_STATUSES:
        status_task_counts[status] = len(
            {row["task_id"] for row in rows if row["match_status"] == status}
        )
    if len(task_ids) != EXPECTED_STAGING_TASKS:
        errors.append(f"staging 업무 수 불일치: {len(task_ids)}")
    if len(rows) != EXPECTED_CONTACT_ROWS:
        errors.append(f"연락처 행 수 불일치: {len(rows)}")
    if sum(row["is_primary"] for row in rows) != EXPECTED_PRIMARY_ROWS:
        errors.append("primary 행 수 불일치")
    if status_task_counts["confirmed_multiple"] != EXPECTED_CONFIRMED_MULTIPLE_TASKS:
        errors.append("confirmed_multiple 업무 수 불일치")
    if status_task_counts["conditional"] != EXPECTED_CONDITIONAL_TASKS:
        errors.append("conditional 업무 수 불일치")

    by_task: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_task.setdefault(row["task_id"], []).append(row)
    for task_id in ("A011", "F101"):
        task_rows = by_task.get(task_id, [])
        if len(task_rows) != 1 or task_rows[0]["phone"] != "031-5189-4364" or not task_rows[0]["is_primary"]:
            errors.append(f"{task_id} primary 검증 실패")
    expected_a012 = {
        ("031-5189-4364", "대표전화", 1),
        ("031-5189-4344", "흉부 X선", 0),
        ("031-5189-4369", "검체검사", 0),
        ("031-5189-4368", "진단검사실", 0),
        ("031-5189-4377", "민원접수", 0),
    }
    actual_a012 = {
        (row["phone"], row["label"], row["is_primary"])
        for row in by_task.get("A012", [])
    }
    if actual_a012 != expected_a012:
        errors.append(f"A012 연락처 구성 불일치: {sorted(actual_a012)}")
    if any(
        row["phone"] == EXCLUDED_PROTECTED_PHONE
        for row in rows
        if row["task_id"] in PROTECTED_TASK_IDS
    ):
        errors.append("서남부권 결핵 번호 031-5189-4354가 보호 업무에 포함됨")
    if errors:
        raise TrialValidationError("; ".join(errors))


CONTACT_COLUMNS = (
    "task_id",
    "phone",
    "display_phone",
    "label",
    "note",
    "contact_role",
    "condition_text",
    "is_primary",
    "source_url",
    "source_urls_json",
    "source_sheet",
    "source_row",
    "verified_at",
    "match_status",
    "active",
)


def apply_contact_rows(
    connection: sqlite3.Connection,
    rows: list[dict[str, Any]],
    importer: Any,
) -> dict[str, int]:
    """Apply validated rows inside a caller-owned transaction."""

    validate_contact_rows(rows, importer)
    if not connection.in_transaction:
        raise TrialValidationError("연락처 적용에는 외부 transaction이 필요합니다.")

    task_ids = sorted({row["task_id"] for row in rows})
    placeholders = ",".join("?" for _ in task_ids)
    existing_task_ids = {
        row[0]
        for row in connection.execute(
            f"SELECT id FROM tasks WHERE id IN ({placeholders})", task_ids
        ).fetchall()
    }
    missing_task_ids = sorted(set(task_ids) - existing_task_ids)
    if missing_task_ids:
        raise TrialValidationError(f"존재하지 않는 task_id: {', '.join(missing_task_ids)}")

    update_assignments = ", ".join(
        f"{column} = ?" for column in CONTACT_COLUMNS if column not in {"task_id", "phone", "label"}
    )
    update_columns = [
        column for column in CONTACT_COLUMNS if column not in {"task_id", "phone", "label"}
    ]
    insert_columns = ", ".join(CONTACT_COLUMNS)
    insert_placeholders = ", ".join("?" for _ in CONTACT_COLUMNS)
    inserted = 0
    updated = 0
    connection.execute(
        f"UPDATE task_contacts SET active = 0 WHERE task_id IN ({placeholders})",
        task_ids,
    )
    for row in rows:
        cursor = connection.execute(
            f"""
            UPDATE task_contacts
            SET {update_assignments}
            WHERE task_id = ? AND phone = ? AND label = ?
            """,
            [row[column] for column in update_columns]
            + [row["task_id"], row["phone"], row["label"]],
        )
        if cursor.rowcount:
            updated += 1
            continue
        connection.execute(
            f"INSERT INTO task_contacts({insert_columns}) VALUES ({insert_placeholders})",
            [row[column] for column in CONTACT_COLUMNS],
        )
        inserted += 1
    return {"inserted": inserted, "updated": updated}


def contact_snapshot(connection: sqlite3.Connection) -> dict[str, Any]:
    columns = [row[1] for row in connection.execute("PRAGMA table_info(task_contacts)")]
    rows = [
        tuple(row)
        for row in connection.execute(
            f"SELECT {', '.join(columns)} FROM task_contacts ORDER BY id"
        ).fetchall()
    ]
    sequence = connection.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'task_contacts'"
    ).fetchone()
    encoded = json.dumps(
        {"columns": columns, "rows": rows, "sequence": sequence[0] if sequence else None},
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "row_count": len(rows),
        "rows": rows,
        "sequence": sequence[0] if sequence else None,
    }


def core_table_snapshot(connection: sqlite3.Connection) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for table in ("tasks", "aliases", "event_logs"):
        columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
        rows = connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
        encoded = json.dumps(
            [columns, [tuple(row) for row in rows]],
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
        result[table] = {
            "count": len(rows),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }
    return result


def fetch_contacts_by_task(connection: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT task_id, phone, display_phone, label, note, contact_role,
               condition_text, is_primary, source_url, source_sheet,
               source_row, verified_at, match_status, active
        FROM task_contacts
        WHERE active = 1
        ORDER BY task_id, is_primary DESC, label, phone
        """
    ).fetchall()
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(row["task_id"], []).append(dict(row))
    return result


def insert_row(connection: sqlite3.Connection, row: dict[str, Any]) -> None:
    columns = ", ".join(CONTACT_COLUMNS)
    placeholders = ", ".join("?" for _ in CONTACT_COLUMNS)
    connection.execute(
        f"INSERT INTO task_contacts({columns}) VALUES ({placeholders})",
        [row[column] for column in CONTACT_COLUMNS],
    )


def expect_integrity_error(connection: sqlite3.Connection, name: str, action) -> bool:
    connection.execute(f"SAVEPOINT {name}")
    rejected = False
    try:
        action()
    except sqlite3.IntegrityError:
        rejected = True
    finally:
        connection.execute(f"ROLLBACK TO {name}")
        connection.execute(f"RELEASE {name}")
    return rejected


def validate_constraints(
    connection: sqlite3.Connection,
    rows: list[dict[str, Any]],
) -> dict[str, bool]:
    duplicate_row = next(row for row in rows if not row["is_primary"])
    primary_template = next(row for row in rows if row["task_id"] == "A011")
    second_primary = dict(primary_template)
    second_primary.update(
        phone="031-000-0000",
        display_phone="031-000-0000",
        label="제약 검증용 두 번째 대표전화",
    )
    orphan = dict(duplicate_row)
    orphan.update(task_id="Z999", label="제약 검증용 고아 연락처")
    return {
        "natural_key_duplicate_rejected": expect_integrity_error(
            connection, "duplicate_key_check", lambda: insert_row(connection, duplicate_row)
        ),
        "second_active_primary_rejected": expect_integrity_error(
            connection, "primary_check", lambda: insert_row(connection, second_primary)
        ),
        "orphan_task_id_rejected": expect_integrity_error(
            connection, "orphan_check", lambda: insert_row(connection, orphan)
        ),
    }


def validate_database(connection: sqlite3.Connection) -> dict[str, Any]:
    duplicate_count = connection.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT task_id, phone, label
            FROM task_contacts
            GROUP BY task_id, phone, label
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    primary_duplicate_count = connection.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT task_id
            FROM task_contacts
            WHERE active = 1 AND is_primary = 1
            GROUP BY task_id
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    orphan_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM task_contacts AS contact
        LEFT JOIN tasks AS task ON task.id = contact.task_id
        WHERE task.id IS NULL
        """
    ).fetchone()[0]
    foreign_key_check = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
    integrity_rows = [row[0] for row in connection.execute("PRAGMA integrity_check")]
    active_rows = connection.execute(
        "SELECT COUNT(*) FROM task_contacts WHERE active = 1"
    ).fetchone()[0]
    total_rows = connection.execute("SELECT COUNT(*) FROM task_contacts").fetchone()[0]
    primary_rows = connection.execute(
        "SELECT COUNT(*) FROM task_contacts WHERE active = 1 AND is_primary = 1"
    ).fetchone()[0]
    staging_tasks = connection.execute(
        "SELECT COUNT(DISTINCT task_id) FROM task_contacts WHERE active = 1"
    ).fetchone()[0]
    multiple_row_tasks = connection.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT task_id FROM task_contacts
            WHERE active = 1
            GROUP BY task_id HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    return {
        "total_contact_rows": total_rows,
        "active_contact_rows": active_rows,
        "staging_task_count": staging_tasks,
        "primary_contact_rows": primary_rows,
        "tasks_with_multiple_contact_rows": multiple_row_tasks,
        "duplicate_count": duplicate_count,
        "primary_duplicate_count": primary_duplicate_count,
        "orphan_task_id_count": orphan_count,
        "foreign_key_check": foreign_key_check,
        "integrity_check": integrity_rows,
    }


def run_temporary_trial(
    source_db: Path = DEFAULT_DB,
    workbook: Path = DEFAULT_WORKBOOK,
    tasks_path: Path = DEFAULT_TASKS,
    schema_path: Path = DEFAULT_SCHEMA,
    *,
    expected_workbook_sha256: str | None = None,
    contact_matches_path: Path = CONTACT_MATCHES_PATH,
) -> dict[str, Any]:
    for path in (source_db, workbook, tasks_path, schema_path):
        if not path.is_file():
            raise TrialValidationError(f"필수 파일이 없습니다: {path}")

    live_before = {
        "sha256": sha256_file(source_db),
        "counts": database_counts(source_db),
        "contact_matches_exists": contact_matches_path.exists(),
    }
    importer = load_importer()
    approved_workbook_sha256 = expected_workbook_sha256 or importer.EXPECTED_WORKBOOK_SHA256
    payload, dry_run = importer.run_import(
        workbook,
        tasks_path,
        source_db,
        expected_sha256=approved_workbook_sha256,
    )
    if not dry_run["validation_passed"]:
        raise TrialValidationError(f"기존 importer 검증 실패: {dry_run['errors']}")
    rows = build_contact_rows(
        payload,
        importer,
        expected_workbook_sha256=approved_workbook_sha256,
    )
    held_tasks = dry_run["summary"]["held_for_review_count"]
    if held_tasks != EXPECTED_HELD_TASKS:
        raise TrialValidationError(f"보류 업무 수 불일치: {held_tasks}")

    temporary_report: dict[str, Any]
    temporary_path_text = ""
    with tempfile.TemporaryDirectory(prefix="task-contacts-") as directory:
        temporary_db = Path(directory) / "health_search.contact-trial.db"
        temporary_path_text = str(temporary_db)
        backup_database(source_db, temporary_db)
        with closing(sqlite3.connect(temporary_db, isolation_level=None)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            backup_core = core_table_snapshot(connection)

            try:
                connection.execute("BEGIN IMMEDIATE")
                migrate_schema(connection, schema_path)
                migrate_schema(connection, schema_path)
                schema_columns = [
                    row[1] for row in connection.execute("PRAGMA table_info(task_contacts)")
                ]
                first_apply = apply_contact_rows(connection, rows, importer)
                first_validation = validate_database(connection)
                first_snapshot = contact_snapshot(connection)
                first_core = core_table_snapshot(connection)
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise

            connection.execute(
                """
                CREATE TEMP TRIGGER force_contact_rollback
                BEFORE UPDATE ON task_contacts
                WHEN NEW.task_id = 'A012' AND NEW.active = 1
                BEGIN
                    SELECT RAISE(ABORT, 'forced task_contacts rollback test');
                END
                """
            )
            forced_failure_seen = False
            try:
                connection.execute("BEGIN IMMEDIATE")
                migrate_schema(connection, schema_path)
                apply_contact_rows(connection, rows, importer)
            except sqlite3.IntegrityError as error:
                forced_failure_seen = "forced task_contacts rollback test" in str(error)
                connection.rollback()
            finally:
                if connection.in_transaction:
                    connection.rollback()
                connection.execute("DROP TRIGGER IF EXISTS force_contact_rollback")
            rollback_snapshot = contact_snapshot(connection)
            rollback_passed = forced_failure_seen and rollback_snapshot == first_snapshot

            try:
                connection.execute("BEGIN IMMEDIATE")
                migrate_schema(connection, schema_path)
                second_apply = apply_contact_rows(connection, rows, importer)
                second_validation = validate_database(connection)
                second_snapshot = contact_snapshot(connection)
                second_core = core_table_snapshot(connection)
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            constraint_results = validate_constraints(connection, rows)
            contacts_by_task = fetch_contacts_by_task(connection)

            temporary_report = {
                "backup_api_used": True,
                "schema_reapplied_successfully": True,
                "schema_columns": schema_columns,
                "rollback": {
                    "forced_failure_seen": forced_failure_seen,
                    "state_unchanged": rollback_snapshot == first_snapshot,
                    "passed": rollback_passed,
                },
                "first_apply": first_apply,
                "second_apply": second_apply,
                "idempotence": {
                    "row_count_unchanged": first_snapshot["row_count"] == second_snapshot["row_count"],
                    "logical_sha256_unchanged": first_snapshot["sha256"] == second_snapshot["sha256"],
                    "sequence_unchanged": first_snapshot["sequence"] == second_snapshot["sequence"],
                    "passed": first_snapshot == second_snapshot,
                },
                "constraints": constraint_results,
                "first_validation": first_validation,
                "second_validation": second_validation,
                "core_tables_unchanged": backup_core == first_core == second_core,
                "contacts_by_task": contacts_by_task,
                "core_contacts": {
                    task_id: contacts_by_task.get(task_id, [])
                    for task_id in ("A011", "A012", "F101")
                },
            }

    live_after = {
        "sha256": sha256_file(source_db),
        "counts": database_counts(source_db),
        "contact_matches_exists": contact_matches_path.exists(),
    }
    validation = temporary_report["second_validation"]
    errors: list[str] = []
    if live_before != live_after:
        errors.append("실제 DB 또는 contact_matches 존재 상태가 작업 전후 달라졌습니다.")
    if live_before["counts"] != EXPECTED_LIVE_COUNTS:
        errors.append(f"실제 DB 기준 수량 불일치: {live_before['counts']}")
    if not temporary_report["rollback"]["passed"]:
        errors.append("강제 오류 rollback 시험 실패")
    if not temporary_report["idempotence"]["passed"]:
        errors.append("재실행 동일성 시험 실패")
    if not all(temporary_report["constraints"].values()):
        errors.append(f"DB 제약 시험 실패: {temporary_report['constraints']}")
    if not temporary_report["core_tables_unchanged"]:
        errors.append("임시 DB의 기존 핵심 테이블이 변경됨")
    expected_validation = {
        "total_contact_rows": EXPECTED_CONTACT_ROWS,
        "active_contact_rows": EXPECTED_CONTACT_ROWS,
        "staging_task_count": EXPECTED_STAGING_TASKS,
        "primary_contact_rows": EXPECTED_PRIMARY_ROWS,
        "tasks_with_multiple_contact_rows": 20,
        "duplicate_count": 0,
        "primary_duplicate_count": 0,
        "orphan_task_id_count": 0,
        "foreign_key_check": [],
        "integrity_check": ["ok"],
    }
    if validation != expected_validation:
        errors.append(f"임시 DB 검증값 불일치: {validation}")

    return {
        "validation_passed": not errors,
        "errors": errors,
        "source": {
            "workbook": str(workbook.resolve()),
            "workbook_sha256": sha256_file(workbook),
            "sheet": importer.FINAL_SHEET,
            "schema": str(schema_path.resolve()),
        },
        "counts": {
            "staging_task_count": EXPECTED_STAGING_TASKS,
            "actual_contact_row_count": EXPECTED_CONTACT_ROWS,
            "primary_contact_row_count": EXPECTED_PRIMARY_ROWS,
            "confirmed_multiple_task_count": EXPECTED_CONFIRMED_MULTIPLE_TASKS,
            "conditional_task_count": EXPECTED_CONDITIONAL_TASKS,
            "held_task_count": EXPECTED_HELD_TASKS,
            "tasks_with_multiple_contact_rows": 20,
        },
        "temporary_database": {
            "path_during_test": temporary_path_text,
            "deleted_after_test": True,
            **temporary_report,
        },
        "live_database": {
            "before": live_before,
            "after": live_after,
            "unchanged": live_before == live_after,
            "writes": 0,
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run_temporary_trial(args.source_db, args.workbook, args.tasks, args.schema)
    except (OSError, ValueError, sqlite3.Error, TrialValidationError) as error:
        print(json.dumps({"validation_passed": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
