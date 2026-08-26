import json
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def main():
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    tasks = json.loads((ROOT / "data" / "tasks.json").read_text(encoding="utf-8"))
    existing_rows = client.table("tasks").select("id").execute().data or []
    existing_ids = {row["id"] for row in existing_rows}
    for task in tasks:
        aliases = task.get("aliases", [])
        # 공식 확인을 거쳐 별도로 입력한 연락처 필드는 이 이관 스크립트가 덮어쓰지 않는다.
        row = {
            "id": task.get("id"),
            "name": task.get("name"),
            "representative": task.get("representative"),
            "department": task.get("department"),
            "team": task.get("team"),
            "floor": task.get("floor"),
            "place": task.get("place"),
            "route": task.get("route"),
            "question": task.get("question"),
            "caution": task.get("caution"),
            "script": task.get("script"),
            "priority": task.get("priority", 0),
            "status": task.get("status"),
            "source": task.get("source"),
            "note": task.get("note"),
            "location_condition": task.get("locationCondition", ""),
            "active": True,
        }
        if row["id"] in existing_ids:
            client.table("tasks").update(row).eq("id", row["id"]).execute()
        else:
            client.table("tasks").insert(row).execute()
            existing_ids.add(row["id"])
        client.table("aliases").delete().eq("task_id", row["id"]).execute()
        if aliases:
            client.table("aliases").insert([
                {"task_id": row["id"], "text": a.get("text"), "weight": a.get("weight", 1), "type": a.get("type")}
                for a in aliases
            ]).execute()
    source_ids = {task["id"] for task in tasks}
    missing_ids = [task_id for task_id in existing_ids if task_id not in source_ids]
    if missing_ids:
        client.table("tasks").update({"active": False}).in_("id", missing_ids).execute()
    print(f"Supabase 이관 완료: {len(tasks)}건")
    print(f"원본에서 사라져 비활성화한 업무: {len(missing_ids)}건")


if __name__ == "__main__":
    main()
