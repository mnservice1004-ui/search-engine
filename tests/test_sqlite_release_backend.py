import sqlite3
from unittest.mock import Mock

import pytest

import db


@pytest.mark.parametrize(
    "operation",
    (
        db.get_all_tasks,
        lambda: db.get_task("A011"),
        lambda: db.get_contacts_by_task_ids(["A011"]),
        lambda: db.get_contacts_by_task_ids([]),
        lambda: db.log_event("search"),
        db.get_event_rows,
    ),
)
def test_non_sqlite_backend_is_rejected_before_supabase_access(
    monkeypatch, operation
):
    monkeypatch.setenv("DATA_BACKEND", "supabase")
    supabase_client = Mock(side_effect=AssertionError("Supabase access is forbidden"))
    monkeypatch.setattr(db, "_supabase", supabase_client)

    with pytest.raises(
        db.UnsupportedDataBackendError,
        match="unsupported in this release",
    ):
        operation()

    supabase_client.assert_not_called()


def test_sqlite_backend_name_is_normalized_and_requires_contact_migration(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_BACKEND", "  SQLite  ")

    assert db._backend() == "sqlite"

    database = tmp_path / "missing-task-contacts.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE tasks(id TEXT PRIMARY KEY)")
    monkeypatch.setenv("SQLITE_PATH", str(database))

    with pytest.raises(
        db.TaskContactsMigrationRequiredError,
        match="approved task_contacts migration",
    ):
        db.get_contacts_by_task_ids(["A011"])

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name = 'task_contacts'"
        ).fetchone()[0] == 0
