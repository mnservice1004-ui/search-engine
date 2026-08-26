import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent


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
    return os.getenv("DATA_BACKEND", "sqlite").lower()


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
