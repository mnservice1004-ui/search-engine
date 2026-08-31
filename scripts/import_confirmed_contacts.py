"""Validate and stage the final official contact workbook.

The command is deliberately dry-run by default.  It never writes to SQLite.
Use ``--write`` only to materialize the validated JSON staging file; applying
that file to either database is a separate, explicitly approved operation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = (
    ROOT
    / "data"
    / "source"
    / "동탄구보건소_검색업무별_공식연락처_확정대조_2026-08-28.xlsx"
)
DEFAULT_TASKS = ROOT / "data" / "tasks.json"
DEFAULT_DB = ROOT / "data" / "health_search.db"
DEFAULT_OUTPUT = ROOT / "data" / "contact_matches.json"
EXPECTED_WORKBOOK_SHA256 = "95862ee7a5bfdf7e349208ae6eeafe19353a1ff8bf97f975d9fd18937a7a253e"
FINAL_SHEET = "PDF대조_확정_63"
SUPPLEMENT_SHEET = "업무별_연락처_63"
EVIDENCE_SHEET = "PDF내선_근거_48"
ADMIN_EVIDENCE_SHEET = "보건행정과_내선_25"

FINAL_HEADERS = (
    "업무ID",
    "검색 업무명",
    "최종 부서",
    "최종 팀",
    "최종 상태",
    "최종 대표전화",
    "최종 추가연락처",
    "PDF 대조판정",
    "PDF 확인 내선",
    "PDF 근거 업무",
    "PDF 근거 위치",
    "기존 상태",
    "기존 대표전화",
    "검색엔진 반영 권고",
    "확정일",
)
SUPPLEMENT_HEADERS = (
    "업무ID",
    "대표 연락처 역할",
    "적용 조건",
    "공식 출처 URL",
    "공식 매칭 근거",
)
EVIDENCE_HEADERS = (
    "정규화 연락처",
    "분장사무 요약",
    "예외·비고",
    "출처 문서",
)

ELIGIBLE_STATUSES = {"confirmed", "confirmed_multiple", "conditional"}
HOLD_STATUSES = {"ambiguous", "conflict", "probable_review", "unmatched"}
ALLOWED_STATUSES = ELIGIBLE_STATUSES | HOLD_STATUSES
EXPECTED_STATUS_COUNTS = {
    "confirmed": 31,
    "confirmed_multiple": 9,
    "conditional": 11,
    "ambiguous": 4,
    "conflict": 1,
    "probable_review": 2,
    "unmatched": 5,
}

PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:(0\d{1,2})[-\s]?(\d{3,4})[-\s]?(\d{4})|(1\d{3})[-\s]?(\d{4}))(?!\d)"
)
PHONE_CANONICAL_PATTERN = re.compile(r"(?:0\d{1,2}-\d{3,4}-\d{4}|1\d{3}-\d{4})\Z")
ID_PATTERN = re.compile(r"[A-Z]\d{3}\Z")

CORE_EXPECTATIONS = {
    "M005": {
        "department": "건강증진과",
        "team": "모자보건팀",
        "primary": "031-5189-6944",
        "additional": set(),
    },
    "M007": {
        "department": "건강증진과",
        "team": "모자보건팀",
        "primary": "031-5189-5076",
        "additional": {"031-5189-5075", "031-5189-4370", "031-5189-5085"},
    },
    "R002": {
        "department": "건강증진과",
        "team": "지역보건팀",
        "primary": "031-5189-5032",
        "additional": set(),
    },
    "A005": {
        "department": "건강증진과",
        "team": "모자보건팀",
        "primary": "031-5189-5076",
        "additional": set(),
    },
}


class ValidationError(RuntimeError):
    """Raised when a workbook cannot be staged safely."""


def text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def iso_date(value: Any) -> str | None:
    if value is None or text(value) == "":
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()[:10]
    return text(value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_phone(match: re.Match[str]) -> str:
    if match.group(1):
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return f"{match.group(4)}-{match.group(5)}"


def parse_phone_entries(value: Any, *, deduplicate: bool = True) -> list[dict[str, str]]:
    """Extract only explicit full numbers and explicit shared-prefix suffixes.

    Evidence columns are intentionally never passed to this function.  A value
    such as ``25번 번호는 잘림`` therefore cannot create a guessed number.
    """

    raw_value = text(value)
    if not raw_value or raw_value.casefold() in {"nan", "none", "null"}:
        return []

    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for segment in re.split(r"[;\n]+", raw_value):
        segment = segment.strip()
        if not segment:
            continue
        matches = list(PHONE_PATTERN.finditer(segment))
        if not matches:
            continue

        parenthetical_notes = [item.strip() for item in re.findall(r"\(([^()]*)\)", segment) if item.strip()]
        residue = PHONE_PATTERN.sub("", segment)
        residue = re.sub(r"[·]\s*\d{4}(?!\d)", "", residue)
        residue = re.sub(r"\([^()]*\)", "", residue)
        residue = residue.strip(" \t,;/·-–—")
        notes = list(parenthetical_notes)
        if residue:
            notes.insert(0, residue)
        note = "; ".join(dict.fromkeys(notes))

        for index, match in enumerate(matches):
            phone = canonical_phone(match)
            candidates = [phone]
            next_start = matches[index + 1].start() if index + 1 < len(matches) else len(segment)
            tail = segment[match.end():next_start]
            if match.group(1):
                prefix = f"{match.group(1)}-{match.group(2)}-"
                candidates.extend(
                    f"{prefix}{suffix}"
                    for suffix in re.findall(r"[·]\s*(\d{4})(?!\d)", tail)
                )

            for candidate in candidates:
                if not PHONE_CANONICAL_PATTERN.fullmatch(candidate):
                    continue
                if deduplicate and candidate in seen:
                    continue
                seen.add(candidate)
                entries.append({"phone": candidate, "note": note, "raw": segment})
    return entries


def find_unparsed_phone_fragments(value: Any) -> list[str]:
    """Return contact-cell fragments that look numeric but are not valid phones."""

    fragments: list[str] = []
    for segment in re.split(r"[;\n]+", text(value)):
        segment = segment.strip()
        if not segment:
            continue
        if not PHONE_PATTERN.search(segment):
            fragments.append(segment)
            continue
        residue = PHONE_PATTERN.sub("", segment)
        residue = re.sub(r"[·]\s*\d{4}(?!\d)", "", residue)
        residue = re.sub(r"\([^()]*\)", "", residue)
        if re.search(r"(?<!\d)\d[\d\s-]{4,}\d(?!\d)", residue):
            fragments.append(segment)
    return fragments


def read_records(workbook: Any, sheet_name: str, required_headers: tuple[str, ...]) -> list[dict[str, Any]]:
    if sheet_name not in workbook.sheetnames:
        raise ValidationError(f"필수 시트가 없습니다: {sheet_name}")
    rows = workbook[sheet_name].iter_rows(values_only=True)
    try:
        header_row = next(rows)
    except StopIteration as error:
        raise ValidationError(f"빈 시트입니다: {sheet_name}") from error
    headers = [text(value) for value in header_row]
    missing = [header for header in required_headers if header not in headers]
    if missing:
        raise ValidationError(f"{sheet_name} 필수 열 누락: {', '.join(missing)}")
    if len([header for header in headers if header]) != len(set(header for header in headers if header)):
        raise ValidationError(f"{sheet_name}에 중복 열 이름이 있습니다.")

    records: list[dict[str, Any]] = []
    for excel_row, values in enumerate(rows, start=2):
        if not any(value is not None and text(value) != "" for value in values):
            continue
        padded = list(values) + [None] * max(0, len(headers) - len(values))
        record = dict(zip(headers, padded))
        record["_excel_row"] = excel_row
        records.append(record)
    return records


def load_tasks(path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValidationError("data/tasks.json의 최상위 값은 배열이어야 합니다.")
    by_id: dict[str, dict[str, Any]] = {}
    for task in raw:
        task_id = text(task.get("id"))
        if not ID_PATTERN.fullmatch(task_id):
            raise ValidationError(f"잘못된 검색엔진 업무 ID: {task_id!r}")
        if task_id in by_id:
            raise ValidationError(f"data/tasks.json 중복 업무 ID: {task_id}")
        by_id[task_id] = task
    return raw, by_id


def load_db_snapshot(path: Path) -> dict[str, Any]:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute(
            """
            SELECT id, name, department, team, phone, contact_role,
                   contact_name, contact_verified_at
            FROM tasks WHERE active = 1 ORDER BY id
            """
        ).fetchall()
        alias_count = connection.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
        event_count = connection.execute("SELECT COUNT(*) FROM event_logs").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    return {
        "tasks": {row["id"]: dict(row) for row in rows},
        "active_task_count": len(rows),
        "alias_count": alias_count,
        "event_count": event_count,
        "integrity_check": integrity,
    }


def extract_urls(value: Any) -> list[str]:
    urls = []
    for url in re.findall(r"https?://[^\s;]+", text(value)):
        cleaned = url.rstrip(").,]")
        if cleaned not in urls:
            urls.append(cleaned)
    return urls


def build_role_lookup(evidence_rows: list[dict[str, Any]]) -> dict[str, str]:
    roles: dict[str, list[str]] = {}
    for row in evidence_rows:
        role = text(row.get("분장사무 요약"))
        if not role:
            continue
        for entry in parse_phone_entries(row.get("정규화 연락처")):
            roles.setdefault(entry["phone"], [])
            if role not in roles[entry["phone"]]:
                roles[entry["phone"]].append(role)
    return {phone: " / ".join(values) for phone, values in roles.items()}


def merge_phone_entries(primary_value: Any, additional_value: Any) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    positions: dict[str, int] = {}
    for listed_as_primary, value in ((True, primary_value), (False, additional_value)):
        for entry in parse_phone_entries(value):
            phone = entry["phone"]
            if phone in positions:
                current = merged[positions[phone]]
                current["listed_as_primary"] = current["listed_as_primary"] or listed_as_primary
                if entry["note"] and entry["note"] not in current["note"]:
                    current["note"] = "; ".join(filter(None, (current["note"], entry["note"])))
                continue
            positions[phone] = len(merged)
            merged.append(
                {
                    "phone": phone,
                    "note": entry["note"],
                    "raw": entry["raw"],
                    "listed_as_primary": listed_as_primary,
                }
            )
    return merged


def build_staging(
    final_rows: list[dict[str, Any]],
    supplement_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    tasks_by_id: dict[str, dict[str, Any]],
    db_snapshot: dict[str, Any],
    source_path: Path,
    source_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    manual_review: list[dict[str, Any]] = []

    final_ids = [text(row.get("업무ID")) for row in final_rows]
    duplicate_ids = sorted(task_id for task_id, count in Counter(final_ids).items() if count > 1)
    invalid_ids = sorted(task_id for task_id in set(final_ids) if not ID_PATTERN.fullmatch(task_id))
    excel_id_set = set(final_ids)
    task_id_set = set(tasks_by_id)
    db_id_set = set(db_snapshot["tasks"])
    missing_in_excel = sorted(task_id_set - excel_id_set)
    only_in_excel = sorted(excel_id_set - task_id_set)
    db_only = sorted(db_id_set - excel_id_set)
    excel_not_in_db = sorted(excel_id_set - db_id_set)
    if len(final_rows) != 63:
        errors.append(f"확정 시트 업무 수가 63이 아닙니다: {len(final_rows)}")
    if duplicate_ids:
        errors.append(f"엑셀 중복 업무 ID: {', '.join(duplicate_ids)}")
    if invalid_ids:
        errors.append(f"엑셀 잘못된 업무 ID: {', '.join(invalid_ids)}")
    if missing_in_excel:
        errors.append(f"검색엔진에만 있는 업무 ID: {', '.join(missing_in_excel)}")
    if only_in_excel:
        errors.append(f"엑셀에만 있는 업무 ID: {', '.join(only_in_excel)}")
    if db_only:
        errors.append(f"SQLite에만 있는 활성 업무 ID: {', '.join(db_only)}")
    if excel_not_in_db:
        errors.append(f"SQLite에 없는 엑셀 업무 ID: {', '.join(excel_not_in_db)}")

    supplement_ids = [text(row.get("업무ID")) for row in supplement_rows]
    duplicate_supplement_ids = sorted(
        task_id for task_id, count in Counter(supplement_ids).items() if count > 1
    )
    supplement_by_id = {text(row.get("업무ID")): row for row in supplement_rows}
    missing_supplement_ids = sorted(excel_id_set - set(supplement_ids))
    extra_supplement_ids = sorted(set(supplement_ids) - excel_id_set)
    if duplicate_supplement_ids:
        errors.append(f"보조 시트 중복 업무 ID: {', '.join(duplicate_supplement_ids)}")
    if missing_supplement_ids:
        errors.append(f"보조 시트 누락 업무 ID: {', '.join(missing_supplement_ids)}")
    if extra_supplement_ids:
        errors.append(f"보조 시트에만 있는 업무 ID: {', '.join(extra_supplement_ids)}")
    role_lookup = build_role_lookup(evidence_rows)
    status_counts = Counter(text(row.get("최종 상태")) for row in final_rows)
    unknown_statuses = sorted(set(status_counts) - ALLOWED_STATUSES)
    if unknown_statuses:
        errors.append(f"허용되지 않은 최종 상태: {', '.join(unknown_statuses)}")
    if dict(status_counts) != EXPECTED_STATUS_COUNTS:
        errors.append(
            "최종 상태 수량 불일치: "
            + json.dumps(dict(sorted(status_counts.items())), ensure_ascii=False)
        )

    matches: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    contact_change_plan: list[dict[str, Any]] = []
    metadata_changes: list[dict[str, Any]] = []
    name_mismatches: list[dict[str, str]] = []
    invalid_phone_rows: list[str] = []
    duplicate_phone_rows: list[dict[str, Any]] = []
    malformed_phone_fragments: list[dict[str, Any]] = []
    official_url_warnings: list[str] = []

    for row in sorted(final_rows, key=lambda item: text(item.get("업무ID"))):
        task_id = text(row.get("업무ID"))
        status = text(row.get("최종 상태"))
        supplement = supplement_by_id.get(task_id, {})
        task = tasks_by_id.get(task_id, {})
        db_task = db_snapshot["tasks"].get(task_id, {})
        workbook_name = text(row.get("검색 업무명"))
        engine_name = text(task.get("name"))
        if engine_name and workbook_name and engine_name != workbook_name:
            name_mismatches.append(
                {"task_id": task_id, "search_engine": engine_name, "workbook": workbook_name}
            )

        parsed_primary = parse_phone_entries(row.get("최종 대표전화"))
        parsed_additional = parse_phone_entries(row.get("최종 추가연락처"))
        all_occurrences = parse_phone_entries(
            row.get("최종 대표전화"), deduplicate=False
        ) + parse_phone_entries(row.get("최종 추가연락처"), deduplicate=False)
        duplicate_phones = sorted(
            phone for phone, count in Counter(item["phone"] for item in all_occurrences).items() if count > 1
        )
        if duplicate_phones:
            duplicate_phone_rows.append({"task_id": task_id, "phones": duplicate_phones})
        for column in ("최종 대표전화", "최종 추가연락처"):
            fragments = find_unparsed_phone_fragments(row.get(column))
            if fragments:
                malformed_phone_fragments.append(
                    {"task_id": task_id, "column": column, "fragments": fragments}
                )
        raw_contact_text = " ".join(
            filter(None, (text(row.get("최종 대표전화")), text(row.get("최종 추가연락처"))))
        )
        if raw_contact_text and not parsed_primary and not parsed_additional:
            invalid_phone_rows.append(task_id)
        if len(parsed_primary) > 1:
            errors.append(f"{task_id}: 최종 대표전화 셀에 번호가 둘 이상 있습니다.")

        source_urls = extract_urls(supplement.get("공식 출처 URL"))
        for url in source_urls:
            parsed_url = urlparse(url)
            if parsed_url.scheme != "https" or not parsed_url.netloc.lower().endswith("hscity.go.kr"):
                official_url_warnings.append(f"{task_id}: 공식 도메인 확인 필요 - {url}")

        merged = merge_phone_entries(row.get("최종 대표전화"), row.get("최종 추가연락처"))
        base_role = text(supplement.get("대표 연락처 역할"))
        base_condition = text(supplement.get("적용 조건"))
        eligible = status in ELIGIBLE_STATUSES
        contacts: list[dict[str, Any]] = []
        for item in merged:
            is_primary = bool(eligible and item["listed_as_primary"])
            role = base_role if item["listed_as_primary"] and base_role else role_lookup.get(item["phone"], "")
            condition = ""
            if status == "conditional":
                condition = item["note"] or base_condition
            contacts.append(
                {
                    "phone": item["phone"],
                    "role": role or None,
                    "note": item["note"] or None,
                    "condition_text": condition or None,
                    "is_primary": is_primary,
                    "listed_as_primary_in_workbook": bool(item["listed_as_primary"]),
                }
            )

        selected_primary = next((item["phone"] for item in contacts if item["is_primary"]), None)
        primary_count = sum(1 for item in contacts if item["is_primary"])
        if status == "confirmed" and (primary_count != 1 or len(contacts) != 1):
            errors.append(f"{task_id}: confirmed는 대표 연락처 하나만 있어야 합니다.")
        if status == "confirmed_multiple" and (primary_count != 1 or len(contacts) < 2):
            errors.append(f"{task_id}: confirmed_multiple은 대표 1개와 추가 연락처가 필요합니다.")
        if status == "conditional" and (not contacts or primary_count > 1):
            errors.append(f"{task_id}: conditional 연락처 구성이 잘못되었습니다.")
        if status in {"confirmed", "confirmed_multiple"}:
            primary_contact = next((item for item in contacts if item["is_primary"]), None)
            if primary_contact and not primary_contact["role"]:
                errors.append(f"{task_id}: 확정 대표전화의 연락처 역할이 비어 있습니다.")
        if status == "conditional" and any(not item["condition_text"] for item in contacts):
            errors.append(f"{task_id}: 조건부 연락처의 적용 조건이 비어 있습니다.")
        if status in HOLD_STATUSES and primary_count:
            errors.append(f"{task_id}: 보류 상태에 대표 연락처가 생성되었습니다.")
        if status == "unmatched" and contacts:
            errors.append(f"{task_id}: unmatched 상태에 연락처 후보가 있습니다.")

        final_department = text(row.get("최종 부서"))
        final_team = text(row.get("최종 팀"))
        old_department = text(db_task.get("department"))
        old_team = text(db_task.get("team"))
        if final_department != old_department or final_team != old_team:
            metadata_changes.append(
                {
                    "task_id": task_id,
                    "existing": {"department": old_department, "team": old_team},
                    "proposed": {"department": final_department, "team": final_team},
                }
            )

        existing_phone = text(db_task.get("phone")) or None
        if eligible and contacts:
            contact_change_plan.append(
                {
                    "task_id": task_id,
                    "status": status,
                    "existing": {
                        "primary_phone": existing_phone,
                        "contact_role": text(db_task.get("contact_role")) or None,
                        "contact_name": text(db_task.get("contact_name")) or None,
                    },
                    "proposed": {
                        "primary_phone": selected_primary,
                        "contacts": contacts,
                    },
                }
            )
        if selected_primary and selected_primary != existing_phone:
            changes.append(
                {
                    "task_id": task_id,
                    "status": status,
                    "existing_primary_phone": existing_phone,
                    "proposed_primary_phone": selected_primary,
                }
            )

        if status in HOLD_STATUSES:
            manual_review.append(
                {
                    "task_id": task_id,
                    "status": status,
                    "candidate_phones": [item["phone"] for item in contacts],
                    "recommendation": text(row.get("검색엔진 반영 권고")) or None,
                }
            )

        matches.append(
            {
                "task_id": task_id,
                "task_name_snapshot": workbook_name,
                "department": final_department,
                "team": final_team or None,
                "match_status": status,
                "reviewed": eligible,
                "review_required": status in HOLD_STATUSES,
                "primary_phone": selected_primary,
                "contacts": contacts,
                "condition_text": base_condition or None,
                "source_urls": source_urls,
                "verified_at": iso_date(row.get("확정일")),
                "evidence": {
                    "workbook_row": row.get("_excel_row"),
                    "pdf_comparison": text(row.get("PDF 대조판정")) or None,
                    "pdf_extension_evidence": text(row.get("PDF 확인 내선")) or None,
                    "pdf_work_evidence": text(row.get("PDF 근거 업무")) or None,
                    "pdf_location_evidence": text(row.get("PDF 근거 위치")) or None,
                    "matching_basis": text(supplement.get("공식 매칭 근거")) or None,
                    "recommendation": text(row.get("검색엔진 반영 권고")) or None,
                    "raw_primary_phone": text(row.get("최종 대표전화")) or None,
                    "raw_additional_contacts": text(row.get("최종 추가연락처")) or None,
                },
            }
        )

    if invalid_phone_rows:
        errors.append(f"전화번호를 해석하지 못한 업무: {', '.join(invalid_phone_rows)}")
    if duplicate_phone_rows:
        errors.append(
            "최종 연락처 셀의 중복 번호: "
            + ", ".join(
                f"{item['task_id']}({', '.join(item['phones'])})" for item in duplicate_phone_rows
            )
        )
    if malformed_phone_fragments:
        errors.append(
            "잘못되었거나 불완전한 전화번호 조각: "
            + ", ".join(
                f"{item['task_id']}:{item['column']}={item['fragments']}"
                for item in malformed_phone_fragments
            )
        )
    warnings.extend(official_url_warnings)
    if name_mismatches:
        warnings.append(f"업무명 표기 차이 {len(name_mismatches)}건(ID 매칭에는 영향 없음)")

    matches_by_id = {item["task_id"]: item for item in matches}
    core_changes: dict[str, Any] = {}
    for task_id, expected in CORE_EXPECTATIONS.items():
        item = matches_by_id.get(task_id)
        if not item:
            errors.append(f"핵심 검증 업무 누락: {task_id}")
            continue
        additional = {contact["phone"] for contact in item["contacts"] if not contact["listed_as_primary_in_workbook"]}
        required_additional = expected["additional"]
        if (
            item["department"] != expected["department"]
            or (item["team"] or "") != expected["team"]
            or item["primary_phone"] != expected["primary"]
            or not required_additional.issubset(additional)
        ):
            errors.append(f"핵심 변경값 불일치: {task_id}")
        db_task = db_snapshot["tasks"].get(task_id, {})
        core_changes[task_id] = {
            "existing": {
                "department": text(db_task.get("department")),
                "team": text(db_task.get("team")) or None,
                "primary_phone": text(db_task.get("phone")) or None,
            },
            "proposed": {
                "department": item["department"],
                "team": item["team"],
                "primary_phone": item["primary_phone"],
                "additional_phones": [
                    contact["phone"]
                    for contact in item["contacts"]
                    if not contact["listed_as_primary_in_workbook"]
                ],
            },
        }

    payload = {
        "schema_version": 1,
        "source": {
            "file": source_path.name,
            "sha256": source_sha256,
            "expected_sha256": source_sha256,
            "sheet": FINAL_SHEET,
            "evidence_sheets": [EVIDENCE_SHEET, ADMIN_EVIDENCE_SHEET],
        },
        "policy": {
            "eligible_statuses": sorted(ELIGIBLE_STATUSES),
            "review_required_statuses": sorted(HOLD_STATUSES),
            "held_statuses_never_select_primary": True,
        },
        "matches": matches,
    }
    rendered_payload = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    report = {
        "mode": "dry-run",
        "validation_passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "source": {
            "path": str(source_path.resolve()),
            "sha256": source_sha256,
            "expected_sha256": source_sha256,
            "sheet": FINAL_SHEET,
            "evidence_sheets": [EVIDENCE_SHEET, ADMIN_EVIDENCE_SHEET],
        },
        "id_reconciliation": {
            "excel_count": len(final_rows),
            "search_engine_count": len(tasks_by_id),
            "sqlite_active_count": db_snapshot["active_task_count"],
            "matched_count": len(excel_id_set & task_id_set & db_id_set),
            "duplicate_excel_ids": duplicate_ids,
            "missing_in_excel": missing_in_excel,
            "only_in_excel": only_in_excel,
            "sqlite_only": db_only,
            "excel_not_in_sqlite": excel_not_in_db,
        },
        "status_counts": dict(sorted(status_counts.items())),
        "summary": {
            "primary_phone_new_or_changed_count": len(changes),
            "staged_contact_record_count": len(contact_change_plan),
            "multiple_contact_count": status_counts.get("confirmed_multiple", 0),
            "conditional_contact_count": status_counts.get("conditional", 0),
            "held_for_review_count": sum(status_counts.get(status, 0) for status in HOLD_STATUSES),
            "legacy_tasks_phone_candidates": sum(
                1 for item in matches if item["match_status"] == "confirmed" and item["primary_phone"]
            ),
            "department_or_team_change_count": len(metadata_changes),
        },
        "db_read_only_snapshot": {
            "integrity_check": db_snapshot["integrity_check"],
            "active_task_count": db_snapshot["active_task_count"],
            "alias_count": db_snapshot["alias_count"],
            "event_count": db_snapshot["event_count"],
        },
        "primary_phone_changes": changes,
        "contact_change_plan": contact_change_plan,
        "metadata_changes": metadata_changes,
        "core_changes": core_changes,
        "manual_review": manual_review,
        "name_mismatches": name_mismatches,
        "planned_output": str(DEFAULT_OUTPUT.resolve()),
        "planned_output_sha256": hashlib.sha256(rendered_payload.encode("utf-8")).hexdigest(),
        "database_writes": 0,
        "database_backup_created": False,
    }
    return payload, report


def run_import(
    workbook_path: Path,
    tasks_path: Path,
    db_path: Path,
    expected_sha256: str = EXPECTED_WORKBOOK_SHA256,
) -> tuple[dict[str, Any], dict[str, Any]]:
    for required_path in (workbook_path, tasks_path, db_path):
        if not required_path.is_file():
            raise ValidationError(f"필수 파일이 없습니다: {required_path}")
    source_sha256 = sha256_file(workbook_path)
    normalized_expected_sha256 = text(expected_sha256).casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized_expected_sha256):
        raise ValidationError("기대 XLSX SHA-256 형식이 잘못되었습니다.")
    if source_sha256.casefold() != normalized_expected_sha256:
        raise ValidationError(
            f"확정 XLSX SHA-256 불일치: expected={normalized_expected_sha256}, "
            f"actual={source_sha256}"
        )
    tasks, tasks_by_id = load_tasks(tasks_path)
    if len(tasks) != 63:
        raise ValidationError(f"검색엔진 업무 수가 63이 아닙니다: {len(tasks)}")
    db_snapshot = load_db_snapshot(db_path)

    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        final_rows = read_records(workbook, FINAL_SHEET, FINAL_HEADERS)
        supplement_rows = read_records(workbook, SUPPLEMENT_SHEET, SUPPLEMENT_HEADERS)
        evidence_rows = read_records(workbook, EVIDENCE_SHEET, EVIDENCE_HEADERS)
        evidence_rows.extend(
            read_records(workbook, ADMIN_EVIDENCE_SHEET, EVIDENCE_HEADERS)
        )
        payload, report = build_staging(
            final_rows,
            supplement_rows,
            evidence_rows,
            tasks_by_id,
            db_snapshot,
            workbook_path,
            source_sha256,
        )
    finally:
        workbook.close()
    return payload, report


def write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    ) as stream:
        temporary_path = Path(stream.name)
        stream.write(rendered)
    try:
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def validate_output_path(
    output_path: Path,
    protected_paths: tuple[Path, ...],
    *,
    force: bool,
) -> str | None:
    resolved_output = output_path.resolve()
    for protected in protected_paths:
        resolved_protected = protected.resolve()
        if resolved_output == resolved_protected:
            return f"입력 또는 DB 파일을 출력으로 덮어쓸 수 없습니다: {resolved_output}"
        if output_path.exists() and protected.exists():
            try:
                if os.path.samefile(output_path, protected):
                    return f"입력 또는 DB 파일과 동일한 출력 파일입니다: {resolved_output}"
            except OSError:
                pass
    if resolved_output.suffix.casefold() != ".json":
        return "출력 파일 확장자는 .json이어야 합니다."
    if output_path.exists() and not force:
        return f"기존 출력 파일을 보존하기 위해 중단했습니다(--force 필요): {resolved_output}"
    return None


def render_text_report(report: dict[str, Any], output_path: Path, wrote: bool) -> str:
    ids = report["id_reconciliation"]
    summary = report["summary"]
    lines = [
        "공식 연락처 가져오기 검증 결과",
        f"모드: {'JSON 쓰기' if wrote else 'dry-run (파일/DB 쓰기 없음)'}",
        f"검증: {'통과' if report['validation_passed'] else '실패'}",
        f"원본: {report['source']['path']}",
        f"원본 SHA-256: {report['source']['sha256']}",
        (
            "업무 ID: "
            f"엑셀 {ids['excel_count']} / 검색엔진 {ids['search_engine_count']} / "
            f"SQLite {ids['sqlite_active_count']} / 완전 일치 {ids['matched_count']}"
        ),
        "상태: " + ", ".join(f"{key}={value}" for key, value in report["status_counts"].items()),
        f"대표전화 신규·변경 예정: {summary['primary_phone_new_or_changed_count']}건",
        f"연락처 staging 변경 예정 업무: {summary['staged_contact_record_count']}건",
        f"복수 연락처: {summary['multiple_contact_count']}건",
        f"조건부 연락처: {summary['conditional_contact_count']}건",
        f"보류: {summary['held_for_review_count']}건",
        f"단일 tasks.phone 반영 후보(confirmed만): {summary['legacy_tasks_phone_candidates']}건",
        f"부서·팀 변경 제안: {summary['department_or_team_change_count']}건",
        f"예정 출력: {output_path.resolve()}",
        f"DB 쓰기: {report['database_writes']}건",
    ]
    lines.append("\n핵심 4건 기존값 -> 변경값")
    for task_id in ("M005", "M007", "R002", "A005"):
        change = report["core_changes"].get(task_id, {})
        lines.append(
            f"- {task_id}: {json.dumps(change.get('existing'), ensure_ascii=False)} -> "
            f"{json.dumps(change.get('proposed'), ensure_ascii=False)}"
        )
    lines.append("\n대표전화 신규·변경 목록")
    for change in report["primary_phone_changes"]:
        lines.append(
            f"- {change['task_id']} [{change['status']}]: "
            f"{change['existing_primary_phone'] or '(없음)'} -> {change['proposed_primary_phone']}"
        )
    lines.append("\n전체 연락처 staging 변경 계획")
    for change in report["contact_change_plan"]:
        proposed = change["proposed"]
        contacts = ", ".join(
            f"{item['phone']}{' [primary]' if item['is_primary'] else ''}"
            for item in proposed["contacts"]
        )
        lines.append(
            f"- {change['task_id']} [{change['status']}]: "
            f"기존={change['existing']['primary_phone'] or '(없음)'} / "
            f"변경={contacts}"
        )
    lines.append("\n수동 검토 필요")
    for item in report["manual_review"]:
        lines.append(
            f"- {item['task_id']} [{item['status']}]: "
            f"{', '.join(item['candidate_phones']) if item['candidate_phones'] else '후보 없음'}"
        )
    if report["warnings"]:
        lines.append("\n경고")
        lines.extend(f"- {warning}" for warning in report["warnings"])
    if report["errors"]:
        lines.append("\n오류")
        lines.extend(f"- {error}" for error in report["errors"])
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--expected-sha256",
        default=EXPECTED_WORKBOOK_SHA256,
        help="허용할 확정 XLSX의 SHA-256 (기본값은 2026-08-28 확정본)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="검증된 data/contact_matches.json만 생성합니다. SQLite는 절대 변경하지 않습니다.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="기존 JSON staging 파일의 명시적 교체를 허용합니다.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload, report = run_import(
            args.workbook,
            args.tasks,
            args.db,
            expected_sha256=args.expected_sha256,
        )
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error, ValidationError) as error:
        print(f"검증 실패: {error}", file=sys.stderr)
        return 2

    report["planned_output"] = str(args.output.resolve())

    output_error = None
    if args.write:
        output_error = validate_output_path(
            args.output,
            (args.workbook, args.tasks, args.db),
            force=args.force,
        )
        if output_error:
            report["errors"].append(output_error)
            report["validation_passed"] = False

    if args.write and report["validation_passed"]:
        write_payload(args.output, payload)
        report["mode"] = "write-json"
        report["planned_output"] = str(args.output.resolve())
    elif args.write:
        report["errors"].append("검증 오류가 있어 JSON을 생성하지 않았습니다.")

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text_report(report, args.output, args.write and report["validation_passed"]))
    return 0 if report["validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
