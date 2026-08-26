import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "health_search.db"
TASKS_PATH = ROOT / "data" / "tasks.json"
SCHEMA_PATH = ROOT / "sql" / "sqlite_schema.sql"


def main():
    if not TASKS_PATH.exists():
        sys.exit("data/tasks.json이 없습니다. extract_reference.py를 먼저 실행하십시오.")
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    if len({task["id"] for task in tasks}) != len(tasks):
        sys.exit("중복된 업무 ID가 있습니다.")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        # 원본에서 사라진 업무는 삭제하지 않고 비활성화한다.
        # 기존에 공식 확인을 거쳐 입력한 연락처 필드는 덮어쓰지 않는다.
        connection.execute("UPDATE tasks SET active = 0")
        for task in tasks:
            connection.execute(
                """
                INSERT INTO tasks(
                    id, name, representative, department, team, floor, place,
                    route, question, caution, script, priority, status, source,
                    note, location_condition, contact_name, contact_role, phone,
                    contact_verified_at, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    representative = excluded.representative,
                    department = excluded.department,
                    team = excluded.team,
                    floor = excluded.floor,
                    place = excluded.place,
                    route = excluded.route,
                    question = excluded.question,
                    caution = excluded.caution,
                    script = excluded.script,
                    priority = excluded.priority,
                    status = excluded.status,
                    source = excluded.source,
                    note = excluded.note,
                    location_condition = excluded.location_condition,
                    active = 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    task.get("id"), task.get("name"), task.get("representative"),
                    task.get("department"), task.get("team"), task.get("floor"),
                    task.get("place"), task.get("route"), task.get("question"),
                    task.get("caution"), task.get("script"), task.get("priority", 0),
                    task.get("status"), task.get("source"), task.get("note"),
                    task.get("locationCondition", ""), "", "", "", None,
                ),
            )
            connection.execute("DELETE FROM aliases WHERE task_id = ?", (task["id"],))
            for alias in task.get("aliases", []):
                connection.execute(
                    "INSERT INTO aliases(task_id, text, weight, type) VALUES (?, ?, ?, ?)",
                    (task["id"], alias.get("text"), alias.get("weight", 1), alias.get("type")),
                )
        missing_contacts = connection.execute(
            "SELECT COUNT(*) FROM tasks WHERE active = 1 AND COALESCE(phone, '') = ''"
        ).fetchone()[0]
    print(f"SQLite DB 생성/갱신 완료: {DB_PATH}")
    print(f"업무 건수: {len(tasks)}")
    print(f"공식 업무전화 미등록: {missing_contacts}건")


if __name__ == "__main__":
    main()
