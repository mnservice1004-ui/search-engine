"""Server-only deployment data. Operational logs and staff metadata never ship."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

TASK_COLUMNS = ('id', 'name', 'representative', 'department', 'team', 'floor',
                'place', 'route', 'question', 'caution', 'script', 'priority',
                'location_condition')
ALIAS_COLUMNS = ('task_id', 'text', 'weight', 'type')
CONTACT_COLUMNS = ('task_id', 'phone', 'display_phone', 'label', 'contact_role',
                   'condition_text', 'verified_at', 'is_primary')
CATALOG_KEYS = {'schema_version', 'tasks', 'aliases', 'contacts'}


def validate_catalog(payload):
    if set(payload) != CATALOG_KEYS or payload['schema_version'] != 1:
        raise ValueError('Invalid deployment catalog schema')
    for name, columns in [('tasks', TASK_COLUMNS), ('aliases', ALIAS_COLUMNS),
                          ('contacts', CONTACT_COLUMNS)]:
        if not isinstance(payload[name], list):
            raise ValueError(f'Invalid {name} collection')
        for row in payload[name]:
            if not isinstance(row, dict) or set(row) != set(columns):
                raise ValueError(f'Unapproved fields in {name}')
            if any(value is not None and type(value) not in (str, int, bool)
                   for value in row.values()):
                raise ValueError(f'Invalid value in {name}')
    ids = [r['id'] for r in payload['tasks']]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Empty or duplicate task IDs')
    if any(r['task_id'] not in ids for name in ('aliases', 'contacts') for r in payload[name]):
        raise ValueError('Unknown task reference')
    return payload


def export_catalog(source, guidance):
    from public_guidance import serialize_public_task

    source = Path(source).resolve(strict=True)
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        tasks = [dict(r) for r in conn.execute(
            f"SELECT {','.join(TASK_COLUMNS)} FROM tasks WHERE active=1 ORDER BY id")]
        aliases = [dict(r) for r in conn.execute(
            'SELECT a.task_id,a.text,a.weight,a.type FROM aliases a '
            'JOIN tasks t ON t.id=a.task_id WHERE t.active=1 ORDER BY a.id')]
        rows = conn.execute(
            f"SELECT {','.join('c.' + c for c in CONTACT_COLUMNS)} FROM task_contacts c "
            'JOIN tasks t ON t.id=c.task_id WHERE c.active=1 AND t.active=1 '
            'ORDER BY c.task_id,c.is_primary DESC,c.label,c.phone').fetchall()
    by_id = {t['id']: t for t in tasks}
    contacts = []
    for row in rows:
        # Use the exact public serializer, not source-sheet/internal contact notes.
        contact = {'phone': row['phone'], 'display_phone': row['display_phone'],
                   'purpose': row['label'], 'role': row['contact_role'],
                   'condition': row['condition_text'], 'verified_date': row['verified_at'],
                   'is_primary': bool(row['is_primary'])}
        safe = serialize_public_task(by_id[row['task_id']], [contact], guidance)['contacts'][0]
        contacts.append(dict(task_id=row['task_id'], phone=safe['phone'],
                             display_phone=safe['display_phone'], label=safe['purpose'],
                             contact_role=safe['role'], condition_text=safe['condition'],
                             verified_at=safe['verified_date'], is_primary=int(safe['is_primary'])))
    return validate_catalog(dict(schema_version=1, tasks=tasks, aliases=aliases, contacts=contacts))


def build_catalog(source, destination):
    """Create only the disposable server bundle DB, never the operational DB."""
    destination = Path(destination).resolve()
    if destination.name != 'deployment_catalog.db':
        raise ValueError('Refusing to write anything except deployment_catalog.db')
    if destination.exists():
        raise FileExistsError('Use a fresh build directory; existing DB is preserved')
    payload = validate_catalog(json.loads(Path(source).read_text(encoding='utf-8')))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(destination)) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('CREATE TABLE tasks (' + ','.join(
            'id TEXT PRIMARY KEY' if c == 'id' else 'priority INTEGER NOT NULL'
            if c == 'priority' else f'{c} TEXT' for c in TASK_COLUMNS)
            + ',active INTEGER NOT NULL DEFAULT 1)')
        conn.execute('CREATE TABLE aliases (id INTEGER PRIMARY KEY,task_id TEXT REFERENCES tasks(id),'
                     'text TEXT,weight INTEGER,type TEXT)')
        conn.execute('CREATE TABLE task_contacts (id INTEGER PRIMARY KEY,task_id TEXT REFERENCES tasks(id),'
                     'phone TEXT,display_phone TEXT,label TEXT,contact_role TEXT,condition_text TEXT,'
                     'verified_at TEXT,is_primary INTEGER,active INTEGER NOT NULL DEFAULT 1)')
        for table, key, columns in [('tasks', 'tasks', TASK_COLUMNS),
                                    ('aliases', 'aliases', ALIAS_COLUMNS),
                                    ('task_contacts', 'contacts', CONTACT_COLUMNS)]:
            conn.executemany(f"INSERT INTO {table} ({','.join(columns)}) VALUES "
                             f"({','.join('?' for _ in columns)})",
                             [tuple(row[c] for c in columns) for row in payload[key]])
        conn.commit()
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or conn.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Deployment database integrity failed')
    return {key: len(payload[key]) for key in ('tasks', 'aliases', 'contacts')}
