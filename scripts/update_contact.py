import argparse
import os
import re
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
PHONE_RE = re.compile(r"^0\d{8,10}$")


def normalized_phone(value):
    phone = re.sub(r"\D", "", value)
    if not PHONE_RE.fullmatch(phone):
        raise ValueError("공식 업무전화는 지역번호를 포함한 9~11자리 숫자여야 합니다.")
    return phone


def verified_date(value):
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    if parsed > date.today():
        raise ValueError("최종 확인일은 미래 날짜일 수 없습니다.")
    return parsed.isoformat()


def update_sqlite(args, phone, checked_at):
    configured = Path(os.getenv("SQLITE_PATH", "data/health_search.db"))
    db_path = configured if configured.is_absolute() else ROOT / configured
    if not db_path.exists():
        raise FileNotFoundError("SQLite DB가 없습니다. scripts/init_db.py를 먼저 실행하십시오.")

    backup_dir = ROOT / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(db_path, backup_dir / f"health_search_{stamp}.db")

    with sqlite3.connect(db_path) as connection:
        exists = connection.execute(
            "SELECT 1 FROM tasks WHERE id = ?", (args.task_id,)
        ).fetchone()
        if not exists:
            raise ValueError("해당 업무 ID가 없습니다.")
        connection.execute(
            """
            UPDATE tasks
               SET contact_name = ?, contact_role = ?, phone = ?,
                   contact_verified_at = ?, updated_at = CURRENT_TIMESTAMP
             WHERE id = ?
            """,
            (args.contact_name, args.contact_role, phone, checked_at, args.task_id),
        )


def update_supabase(args, phone, checked_at):
    from supabase import create_client

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    response = (
        client.table("tasks")
        .update({
            "contact_name": args.contact_name,
            "contact_role": args.contact_role,
            "phone": phone,
            "contact_verified_at": checked_at,
        })
        .eq("id", args.task_id)
        .execute()
    )
    if not response.data:
        raise ValueError("해당 업무 ID가 없거나 업데이트 권한이 없습니다.")


def main():
    parser = argparse.ArgumentParser(description="공식 확인을 마친 업무 연락처를 안전하게 갱신합니다.")
    parser.add_argument("task_id")
    parser.add_argument("--contact-name", default="")
    parser.add_argument("--contact-role", required=True)
    parser.add_argument("--phone", required=True)
    parser.add_argument("--verified-at", required=True, help="YYYY-MM-DD")
    parser.add_argument("--confirmed-official", action="store_true")
    args = parser.parse_args()

    if not args.confirmed_official:
        raise SystemExit("--confirmed-official 옵션이 필요합니다. 공식 자료 확인 전에는 입력하지 마십시오.")
    phone = normalized_phone(args.phone)
    checked_at = verified_date(args.verified_at)

    if os.getenv("DATA_BACKEND", "sqlite").lower() == "supabase":
        update_supabase(args, phone, checked_at)
        backend = "Supabase"
    else:
        update_sqlite(args, phone, checked_at)
        backend = "SQLite"
    masked = f"{phone[:3]}****{phone[-4:]}"
    print(f"{backend} 연락처 갱신 완료: {args.task_id} / {masked} / 확인일 {checked_at}")


if __name__ == "__main__":
    main()
