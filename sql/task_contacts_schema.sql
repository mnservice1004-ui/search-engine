CREATE TABLE IF NOT EXISTS task_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    phone TEXT NOT NULL CHECK(length(trim(phone)) > 0),
    display_phone TEXT NOT NULL CHECK(length(trim(display_phone)) > 0),
    label TEXT NOT NULL CHECK(length(trim(label)) > 0),
    note TEXT,
    contact_role TEXT,
    condition_text TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK(is_primary IN (0, 1)),
    source_url TEXT NOT NULL CHECK(length(trim(source_url)) > 0),
    source_urls_json TEXT NOT NULL DEFAULT '[]',
    source_sheet TEXT NOT NULL CHECK(length(trim(source_sheet)) > 0),
    source_row INTEGER NOT NULL CHECK(source_row >= 2),
    verified_at TEXT NOT NULL CHECK(length(trim(verified_at)) > 0),
    match_status TEXT NOT NULL CHECK(match_status IN (
        'confirmed', 'confirmed_multiple', 'conditional'
    )),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    UNIQUE(task_id, phone, label)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_task_contacts_one_active_primary
ON task_contacts(task_id)
WHERE is_primary = 1 AND active = 1;

CREATE INDEX IF NOT EXISTS idx_task_contacts_task_active
ON task_contacts(task_id, active);
