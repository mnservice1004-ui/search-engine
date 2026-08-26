CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    representative TEXT,
    department TEXT,
    team TEXT,
    floor TEXT,
    place TEXT,
    route TEXT,
    question TEXT,
    caution TEXT,
    script TEXT,
    priority INTEGER NOT NULL DEFAULT 0,
    status TEXT,
    source TEXT,
    note TEXT,
    location_condition TEXT,
    contact_name TEXT,
    contact_role TEXT,
    phone TEXT,
    contact_verified_at TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    weight INTEGER NOT NULL DEFAULT 1,
    type TEXT,
    UNIQUE(task_id, text)
);

CREATE TABLE IF NOT EXISTS event_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    result_count INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
