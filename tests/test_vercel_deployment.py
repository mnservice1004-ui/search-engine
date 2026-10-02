import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tomllib
from pathlib import Path

import pytest
import db
from deployment_catalog import build_catalog, export_catalog, validate_catalog
from public_guidance import load_public_guidance
from app import app, limiter

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def catalog(tmp_path, public_guidance_contact_db):
    payload = export_catalog(public_guidance_contact_db, load_public_guidance())
    source = tmp_path / 'deployment_catalog.json'
    source.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    destination = tmp_path / 'data/deployment_catalog.db'
    build_catalog(source, destination)
    return source, destination, payload


def test_export_does_not_include_operational_or_private_columns(catalog, public_guidance_contact_db):
    before = hashlib.sha256(public_guidance_contact_db.read_bytes()).hexdigest()
    payload = export_catalog(public_guidance_contact_db, load_public_guidance())
    assert before == hashlib.sha256(public_guidance_contact_db.read_bytes()).hexdigest()
    assert len(payload['tasks']) == 63 and len(payload['aliases']) == 316
    assert not {'event_logs', 'source_row', 'contact_name', 'note', 'source_url'} & set(payload)
    for rows in (payload['tasks'], payload['contacts']):
        assert all(not {'contact_name', 'note', 'source_url', 'source_row', 'source_sheet'} & set(row) for row in rows)


def test_catalog_database_has_no_event_logs_and_integrity(catalog):
    with sqlite3.connect(catalog[1]) as connection:
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {'tasks', 'aliases', 'task_contacts'}
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []


def test_cloud_database_is_fixed_readonly_and_logging_never_writes(catalog, monkeypatch):
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setenv('SQLITE_PATH', 'do-not-use-operational.db')
    monkeypatch.setattr(db, 'ROOT', catalog[1].parents[1])
    before = hashlib.sha256(catalog[1].read_bytes()).hexdigest()
    assert db._sqlite_path() == catalog[1]
    assert len(db.get_all_tasks()) == 63
    with db._sqlite_connection() as connection:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("UPDATE tasks SET name='forbidden'")
    db.log_event('search', result_count=3)
    assert before == hashlib.sha256(catalog[1].read_bytes()).hexdigest()


def test_missing_cloud_catalog_does_not_create_empty_database(monkeypatch, tmp_path):
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setattr(db, 'ROOT', tmp_path)
    with pytest.raises(sqlite3.OperationalError):
        db.get_all_tasks()
    assert not list(tmp_path.rglob('*.db'))


def test_build_refuses_original_database_and_overwrite(catalog, tmp_path):
    with pytest.raises(ValueError):
        build_catalog(catalog[0], tmp_path / 'health_search.db')
    with pytest.raises(FileExistsError):
        build_catalog(catalog[0], catalog[1])


@pytest.mark.parametrize('field', ['event_logs', 'contact_name', 'source_url', 'note'])
def test_catalog_fails_closed_on_extra_fields(catalog, field):
    payload = catalog[2]
    payload['tasks'][0][field] = 'must-not-ship'
    with pytest.raises(ValueError):
        validate_catalog(payload)


def test_cloud_search_matches_existing_public_api(catalog, public_guidance_contact_db, monkeypatch):
    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.setattr(limiter, 'enabled', False)
    monkeypatch.setenv('SQLITE_PATH', str(public_guidance_contact_db))
    monkeypatch.setattr('app.best_effort_log', lambda *args, **kwargs: None)
    client = app.test_client()
    queries = [term for g in load_public_guidance().values() for term in g['public_search_terms']]
    queries += [r['place'] for r in catalog[2]['tasks'] if r['place']]
    queries += ['진료 접수', '민원실', '예방접종', '연명치료', '방사선실', '보건행정과']
    previous = {q: client.post('/api/search', json={'query': q}).json for q in set(queries) if len(q) >= 2}
    details = {r['id']: client.get('/api/tasks/' + r['id']).json for r in catalog[2]['tasks']}
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setattr(db, 'ROOT', catalog[1].parents[1])
    for query, expected in previous.items():
        response = client.post('/api/search', json={'query': query})
        assert response.status_code == 200 and response.json == expected, query
    for task_id, expected in details.items():
        assert client.get('/api/tasks/' + task_id).json == expected, task_id


def test_vercel_config_has_no_secret_env_or_catchall_spa_rewrite():
    config = json.loads((ROOT / 'vercel.json').read_text(encoding='utf-8'))
    assert config['framework'] == 'flask'
    assert config['buildCommand'] == 'python scripts/build_vercel_catalog.py'
    assert not {'env', 'builds'} & set(config)
    rules = (ROOT / '.vercelignore').read_text(encoding='utf-8')
    assert '\n*\n' in rules and '!data/deployment_catalog.json' in rules
    assert '!public/**' in rules  # The approved background uses public/qa assets.
    assert '!data/tasks.json' not in rules and '!data/health_search.db' not in rules


def test_vercel_static_output_is_only_the_public_directory():
    config = json.loads((ROOT / 'vercel.json').read_text(encoding='utf-8'))
    output = (ROOT / config['outputDirectory']).resolve()
    assert output == (ROOT / 'public').resolve()
    assert (output / 'index.html').is_file()
    assert not (ROOT / 'data').resolve().is_relative_to(output)


def test_vercel_cli_traverses_allowed_directories_and_excludes_private_files(tmp_path):
    # Use Vercel's real traversal and ignore filter. It checks directory names
    # without trailing slashes, which differs from a Git path-only check.
    candidates = [parent / '.tools/vercel-cli/node_modules/vercel' for parent in (ROOT, *ROOT.parents)]
    cli = next((path for path in candidates if (path / 'package.json').is_file()), None)
    node = shutil.which('node')
    if cli is None or node is None:
        pytest.skip('Install the isolated Vercel CLI to run its upload traversal regression')
    allowed = {
        'app.py', 'data/deployment_catalog.json', 'data/map_points.json',
        'data/public_guidance.json', 'scripts/build_vercel_catalog.py',
        'public/index.html', 'public/css/style.css', 'public/js/app.js',
        'public/images/map.webp', 'public/data/corridor_routes.json',
        'public/qa/layer-home.js', 'public/qa/assets/sky.png',
    }
    excluded = {
        '.env', 'data/health_search.db', 'data/deployment_catalog.db',
        'data/private.xlsx', 'data/internal.json', 'scripts/export_vercel_catalog.py',
        '.tools/private.txt', 'reports/private.txt', 'public/.env.local',
        'public/private.db',
    }
    for name in allowed | excluded:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('synthetic upload fixture', encoding='utf-8')
    (tmp_path / '.vercelignore').write_text(
        (ROOT / '.vercelignore').read_text(encoding='utf-8'), encoding='utf-8')
    probe = r"""
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [cli, root] = process.argv.slice(1);
const chunks = path.join(cli, 'dist', 'chunks');
const filename = fs.readdirSync(chunks).find(name => name.endsWith('.js') &&
  fs.readFileSync(path.join(chunks, name), 'utf8').includes('function staticFiles(path, { src }, output)'));
if (!filename) throw new Error('Vercel CLI traversal export changed; update this integration probe');
const module = await import(pathToFileURL(path.join(chunks, filename)).href);
const {staticFiles} = module.require_get_files();
const output = {debug() {}, time(_label, promise) { return promise; }};
const files = await staticFiles(root, {}, output);
console.log(JSON.stringify(files.map(file => path.relative(root, file).split(path.sep).join('/')).sort()));
"""
    result = subprocess.run(
        [node, '--input-type=module', '-e', probe, str(cli), str(tmp_path)],
        capture_output=True, text=True, encoding='utf-8', check=True,
        env=dict(os.environ, NO_UPDATE_NOTIFIER='1', VERCEL_TELEMETRY_DISABLED='1'))
    assert set(json.loads(result.stdout)) == allowed


def test_vercel_homepage_rewrite_does_not_intercept_api_routes():
    config = json.loads((ROOT / 'vercel.json').read_text(encoding='utf-8'))
    assert config['rewrites'] == [{'source': '/', 'destination': '/index.html'}]
    assert all(rule['source'] != path for rule in config['rewrites']
               for path in ['/api/health', '/api/search', '/api/tasks/A001', '/api/sms/send'])


def test_python_dependencies_do_not_disappear_when_pyproject_takes_priority():
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    required = [line.strip() for line in (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines()
                if line.strip() and not line.startswith('#')]
    assert sorted(project['dependencies']) == sorted(required)
