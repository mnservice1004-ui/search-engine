import shutil
import sqlite3

import db
import pytest


PUBLIC_FIELDS = {
    "phone",
    "display_phone",
    "purpose",
    "role",
    "condition",
    "verified_date",
    "is_primary",
}
HELD_TASK_IDS = (
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
)


@pytest.fixture
def temporary_api_db(tmp_path, public_guidance_contact_db):
    destination_path = tmp_path / "health_search.db"
    shutil.copy2(public_guidance_contact_db, destination_path)
    return destination_path


def test_bulk_contact_loader_uses_one_query_and_stable_public_shape(
    monkeypatch, temporary_api_db
):
    monkeypatch.setenv("DATA_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(temporary_api_db))
    real_connect = sqlite3.connect
    statements = []

    def traced_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(db.sqlite3, "connect", traced_connect)
    public_guidance_ids = [
        "A001",
        "A003",
        "A007",
        "A019",
        "F103",
        "F108",
        "F201",
        "H001",
        "H002",
        "M002",
        "M003",
        "M004",
        "M005",
        "M006",
        "M008",
    ]
    grouped = db.get_contacts_by_task_ids(
        ["A011", "A012", "F101", "H004", *public_guidance_ids, "A012"]
    )
    contact_selects = [
        statement
        for statement in statements
        if "FROM task_contacts" in statement and statement.lstrip().upper().startswith("SELECT")
    ]

    assert len(contact_selects) == 1
    assert "match_status" not in contact_selects[0]
    assert list(grouped) == ["A011", "A012", "F101", "H004", *public_guidance_ids]
    assert grouped["H004"] == []
    assert all(set(contact) == PUBLIC_FIELDS for rows in grouped.values() for contact in rows)
    assert grouped["A011"][0]["phone"] == "031-5189-4364"
    assert grouped["A011"][0]["is_primary"] is True
    assert len(grouped["A011"]) == 1
    assert grouped["F101"][0]["phone"] == "031-5189-4364"
    assert grouped["F101"][0]["is_primary"] is True
    assert len(grouped["F101"]) == 1
    assert len(grouped["A012"]) == 5
    assert sum(contact["is_primary"] for contact in grouped["A012"]) == 1
    assert [contact["phone"] for contact in grouped["A012"]] == [
        "031-5189-4364",
        "031-5189-4369",
        "031-5189-4377",
        "031-5189-4368",
        "031-5189-4344",
    ]
    assert all(
        contact["phone"] != "031-5189-4354"
        for task_id in ("A011", "A012", "F101")
        for contact in grouped[task_id]
    )
    assert {
        task_id: tuple(contact["phone"] for contact in grouped[task_id])
        for task_id in public_guidance_ids
    } == {
        "A001": ("031-5189-4378",),
        "A003": ("031-5189-4377",),
        "A007": ("031-5189-5093",),
        "A019": ("031-5189-4344",),
        "F103": ("031-5189-4378",),
        "F108": ("031-5189-4377",),
        "F201": ("031-5189-4374",),
        "H001": ("031-5189-4371",),
        "H002": ("031-5189-4374",),
        "M002": ("031-5189-6944",),
        "M003": ("031-5189-6943", "031-5189-4370", "031-5189-5085"),
        "M004": ("031-5189-4370", "031-5189-5085", "031-5189-6944"),
        "M005": ("031-5189-6944", "031-5189-4370", "031-5189-5085"),
        "M006": (
            "031-5189-6944",
            "031-5189-4370",
            "031-5189-5085",
            "031-5189-5023",
        ),
        "M008": ("031-5189-6944",),
    }
    assert all(grouped[task_id][0]["is_primary"] for task_id in public_guidance_ids)
    assert all(
        contact["verified_date"] == "2026-08-28"
        for task_id in public_guidance_ids
        for contact in grouped[task_id]
    )


def test_all_held_tasks_have_empty_contact_arrays(monkeypatch, temporary_api_db):
    monkeypatch.setenv("DATA_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(temporary_api_db))

    grouped = db.get_contacts_by_task_ids(HELD_TASK_IDS)

    assert set(grouped) == set(HELD_TASK_IDS)
    assert all(grouped[task_id] == [] for task_id in HELD_TASK_IDS)
