import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUPPORTED_DATA_BACKEND = "sqlite"


class UnsupportedDataBackendError(RuntimeError):
    """Raised when this SQLite-only release is configured for another backend."""


class TaskContactsMigrationRequiredError(RuntimeError):
    """Raised when the approved task_contacts migration has not been applied."""


def _sqlite_path():
    configured = os.getenv("SQLITE_PATH", "data/health_search.db")
    path = Path(configured)
    return path if path.is_absolute() else ROOT / path


def _sqlite_connection():
    connection = sqlite3.connect(_sqlite_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _supabase():
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def _backend():
    backend = os.getenv("DATA_BACKEND", SUPPORTED_DATA_BACKEND).strip().lower()
    if backend != SUPPORTED_DATA_BACKEND:
        raise UnsupportedDataBackendError(
            f"DATA_BACKEND={backend!r} is unsupported in this release; "
            f"use {SUPPORTED_DATA_BACKEND!r}."
        )
    return backend


def get_all_tasks():
    if _backend() == "supabase":
        response = (
            _supabase().table("tasks")
            .select("*,aliases(*)")
            .eq("active", True)
            .execute()
        )
        return response.data or []

    with _sqlite_connection() as connection:
        task_rows = connection.execute(
            "SELECT * FROM tasks WHERE active = 1 ORDER BY id"
        ).fetchall()
        alias_rows = connection.execute(
            "SELECT task_id, text, weight, type FROM aliases ORDER BY id"
        ).fetchall()
    aliases_by_task = {}
    for row in alias_rows:
        aliases_by_task.setdefault(row["task_id"], []).append(dict(row))
    tasks = []
    for row in task_rows:
        task = dict(row)
        task["aliases"] = aliases_by_task.get(task["id"], [])
        task["locationCondition"] = task.get("location_condition", "")
        tasks.append(task)
    return tasks


def get_task(task_id):
    for task in get_all_tasks():
        if task.get("id") == task_id:
            return task
    return None


def _public_contact(row):
    return {
        "phone": row.get("phone"),
        "display_phone": row.get("display_phone"),
        "purpose": row.get("label"),
        "role": row.get("contact_role"),
        "condition": row.get("condition_text"),
        "verified_date": row.get("verified_at"),
        "is_primary": bool(row.get("is_primary")),
    }


def get_contacts_by_task_ids(task_ids):
    """Return active public contacts grouped by task with one backend query."""

    backend = _backend()
    ordered_ids = list(dict.fromkeys(str(task_id) for task_id in task_ids if task_id))
    contacts_by_task = {task_id: [] for task_id in ordered_ids}
    if not ordered_ids:
        return contacts_by_task

    selected_columns = (
        "task_id,phone,display_phone,label,contact_role,condition_text,"
        "verified_at,is_primary"
    )
    if backend == "supabase":
        response = (
            _supabase().table("task_contacts")
            .select(selected_columns)
            .in_("task_id", ordered_ids)
            .eq("active", True)
            .execute()
        )
        contact_rows = response.data or []
    else:
        placeholders = ",".join("?" for _ in ordered_ids)
        with _sqlite_connection() as connection:
            try:
                rows = connection.execute(
                    f"""
                    SELECT {selected_columns}
                    FROM task_contacts
                    WHERE active = 1 AND task_id IN ({placeholders})
                    ORDER BY task_id, is_primary DESC, label, phone
                    """,
                    ordered_ids,
                ).fetchall()
            except sqlite3.OperationalError as error:
                if "no such table: task_contacts" not in str(error).casefold():
                    raise
                raise TaskContactsMigrationRequiredError(
                    "SQLite task_contacts schema is missing; run the approved "
                    "task_contacts migration before starting this release."
                ) from error
        contact_rows = [dict(row) for row in rows]

    contact_rows.sort(
        key=lambda row: (
            str(row.get("task_id") or ""),
            0 if row.get("is_primary") else 1,
            str(row.get("label") or "").casefold(),
            str(row.get("phone") or ""),
        )
    )
    for row in contact_rows:
        task_id = str(row.get("task_id") or "")
        if task_id in contacts_by_task:
            contacts_by_task[task_id].append(_public_contact(row))
    return contacts_by_task


def log_event(event_type, task_id=None, result_count=None):
    # 검색 원문, IP, 민원인 휴대전화번호는 기록하지 않는다.
    payload = {
        "event_type": event_type,
        "task_id": task_id,
        "result_count": result_count,
    }
    if _backend() == "supabase":
        _supabase().table("event_logs").insert(payload).execute()
        return
    with _sqlite_connection() as connection:
        connection.execute(
            "INSERT INTO event_logs(event_type, task_id, result_count) VALUES (?, ?, ?)",
            (event_type, task_id, result_count),
        )


def get_event_rows():
    if _backend() == "supabase":
        response = _supabase().table("event_logs").select("*").order("created_at", desc=True).limit(5000).execute()
        return response.data or []
    with _sqlite_connection() as connection:
        rows = connection.execute(
            "SELECT id, event_type, task_id, result_count, created_at FROM event_logs ORDER BY created_at DESC LIMIT 5000"
        ).fetchall()
    return [dict(row) for row in rows]
