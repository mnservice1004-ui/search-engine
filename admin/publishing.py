"""Allowlisted, isolated preview and publish jobs driven by the local manager."""
from datetime import datetime
from hashlib import sha1, sha256
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
from uuid import uuid4

import requests
from admin.content_store import ROOT, FILES, PHOTO_PATHS, ContentError, Store, atomic_json, digest, read_json, now

MANAGED = [*FILES.values(), *PHOTO_PATHS, 'public/index.html']
CONFIG = read_json(ROOT / 'admin/release_manifest.json')
PROCESSES = {}


def child_env():
    # No .env or inherited provider credentials reach the preview process.
    allowed = {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'COMSPEC'}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    env.update(PYTHONIOENCODING='utf-8', PYTHON_DOTENV_DISABLED='1', SMS_MODE='mock', ENABLE_LLM='false', DATA_BACKEND='sqlite')
    return env


def spawn(args, **kwargs):
    return subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, **kwargs)


def make_bundle(store, revision, folder):
    folder = Path(folder)
    folder.mkdir(parents=True)
    baseline = {}
    for name in CONFIG['files']:
        path = store.root / name
        if path.is_symlink() or not path.resolve().is_relative_to(store.root):
            raise ContentError('공개 파일 경로를 확인해 주세요.')
        baseline[name] = digest(path)
        dest = folder / name; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    store.materialize(revision, folder)
    (folder / '.vercel').mkdir()
    atomic_json(folder / '.vercel/project.json', CONFIG['project'])
    return baseline


def preview(store, revision):
    run_id = uuid4().hex
    folder = store.home / 'previews' / run_id
    baseline = make_bundle(store, revision, folder)
    from deployment_catalog import build_catalog
    build_catalog(folder / FILES['catalog'], folder / 'data/deployment_catalog.db')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    log = (folder.parent / (run_id + '.log')).open('w', encoding='utf-8')
    process = spawn([sys.executable, str(ROOT / 'admin/preview_server.py'), str(folder), str(port)],
                    cwd=folder, env=child_env(), stdout=log, stderr=log)
    log.close()
    PROCESSES[run_id] = process
    base = f'http://127.0.0.1:{port}'
    for _ in range(50):
        if process.poll() is not None: raise ContentError('미리보기 실행에 실패했습니다. 관리자 도구를 다시 실행해 주세요.')
        try:
            if requests.get(base + '/__manager__/health', timeout=1).json().get('bundle') == run_id: break
        except (requests.RequestException, ValueError): pass
        time.sleep(.2)
    else:
        process.terminate(); raise ContentError('미리보기 시작 시간이 초과됐습니다.')
    api_checks = verify_runtime(base, folder, revision, store, static=True, sms_blocked=True)
    record = dict(id=run_id, revision=revision, url=base, at=now(), baseline=baseline,
                  hashes={n:digest(folder/n) for n in CONFIG['files']}, verified=True, api_checks=api_checks)
    atomic_json(store.home / 'preview.json', record)
    # Only processes started by this interpreter are eligible for termination.
    for key, old in list(PROCESSES.items()):
        if key != run_id:
            if old.poll() is None: old.terminate()
            PROCESSES.pop(key)
    return record


def verify_runtime(base, folder, revision, store, static=False, sms_blocked=False, expected=None):
    session = requests.Session()
    def get(path):
        response = session.get(base + path, timeout=35); response.raise_for_status(); return response
    health = get('/api/health').json()
    payload = store.read(revision)['payload']
    if not health.get('ok') or health.get('task_count') != len(payload['data']['catalog']['tasks']):
        raise ContentError('업무 목록 확인에 실패했습니다.')
    if static:
        for name in CONFIG['files']:
            if name.startswith('public/'):
                response = get('/' + name.removeprefix('public/'))
                if sha256(response.content).hexdigest() != digest(Path(folder) / name):
                    raise ContentError('공개 화면 파일이 배포본과 다릅니다: ' + name)
    # Check all task detail endpoints, not just an HTTP 200 from the homepage.
    checks = {'details':{}, 'searches':{}}
    for task in payload['data']['catalog']['tasks']:
        detail = get('/api/tasks/' + task['id']).json()
        if detail.get('id') != task['id']:
            raise ContentError('업무 상세 확인에 실패했습니다.')
        checks['details'][task['id']] = detail
    for query in ['보건증', '접종', '검사', '산전검사']:
        response = session.post(base + '/api/search', json={'query':query,'limit':100}, timeout=35)
        response.raise_for_status(); body = response.json()
        if 'items' not in body or 'examinations' not in body: raise ContentError('검색 결과 형식 오류')
        checks['searches'][query] = {k:body[k] for k in ['items','examinations','vaccination','services']}
    if sms_blocked and session.post(base + '/api/sms/send', json={}, timeout=5).status_code != 403:
        raise ContentError('미리보기 문자 차단 확인에 실패했습니다.')
    if expected is not None and checks != expected:
        raise ContentError('공개 검색 결과가 확인한 미리보기와 다릅니다.')
    return checks


def search_preview(url, query):
    if not re.fullmatch(r'http://127\.0\.0\.1:\d+', url): raise ContentError('미리보기 주소 오류')
    r = requests.post(url + '/api/search', json={'query':query,'limit':100}, timeout=20)
    r.raise_for_status()
    return r.json()


def cli(args, timeout=600):
    node = shutil.which('node')
    entry = ROOT / '.tools/vercel-cli/node_modules/vercel/dist/index.js'
    auth = ROOT / '.tools/vercel-cli/auth'
    if not node or not entry.is_file():
        raise ContentError('배포 도구가 없습니다. setup_admin.bat을 실행해 주세요.')
    result = subprocess.run([node, str(entry), *args, '--scope', CONFIG['scope'], '--global-config', str(auth)],
                            capture_output=True, text=True, encoding='utf-8', errors='replace',
                            timeout=timeout, cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        # Never expose arbitrary CLI/provider output, which may contain credentials.
        raise ContentError('배포 명령이 실패했습니다. Vercel 로그인 상태와 인터넷 연결을 확인해 주세요.')
    return result.stdout


def start_publish(store, revision, preview_id):
    current_preview = read_json(store.home / 'preview.json')
    if current_preview['revision'] != revision or current_preview['id'] != preview_id:
        raise ContentError('최신 내용을 미리보기에서 먼저 확인해 주세요.')
    worker_lock = Store(root=store.root, home=store.home / 'publisher-lock')
    with worker_lock.lock(), store.lock():
        running = store.home / 'job.json'
        if running.exists():
            prior = read_json(running)
            # A running worker holds the OS lock. A crashed worker releases it.
            if prior.get('status') == 'queued' and time.time() - prior.get('queued_at', 0) < 30:
                raise ContentError('공개 반영이 시작 중입니다. 잠시 후 상태를 확인해 주세요.')
        job = dict(id=uuid4().hex, revision=revision, preview_id=preview_id, status='queued', stage='공개 반영 준비', at=now(), queued_at=time.time())
        atomic_json(running, job)
    log = (store.home / 'publish.log').open('w', encoding='utf-8')
    process = spawn([sys.executable, '-m', 'admin.publishing', str(store.home), job['id']],
                    cwd=ROOT, env=child_env(), stdout=log, stderr=log)
    log.close()
    job['pid'] = process.pid
    # Worker owns subsequent status updates; do not overwrite them here.
    return job


def publish_job(store, job_id):
    with Store(root=store.root, home=store.home / 'publisher-lock').lock():
        return _publish_job(store, job_id)


def _publish_job(store, job_id):
    job = read_json(store.home / 'job.json')
    if job['id'] != job_id: raise ContentError('공개 작업 번호 오류')
    def status(stage, **extra):
        job.update(stage=stage, status='running', **extra); atomic_json(store.home / 'job.json', job)
    promoted = False
    previous = None
    try:
        status('최신 내용과 파일 확인')
        p = read_json(store.home / 'preview.json')
        if p['id'] != job['preview_id'] or p['revision'] != job['revision']:
            raise ContentError('미리보기가 변경됐습니다. 다시 확인해 주세요.')
        if store.read()['id'] != job['revision']: raise ContentError('수정 내용이 변경됐습니다. 다시 확인해 주세요.')
        for n, h in p['baseline'].items():
            if digest(store.root / n) != h: raise ContentError('프로젝트 파일이 변경됐습니다. 미리보기를 다시 생성해 주세요.')
        folder = store.home / 'releases' / job_id / 'runtime'
        make_bundle(store, job['revision'], folder)
        if {n:digest(folder/n) for n in CONFIG['files']} != p['hashes']:
            raise ContentError('미리보기와 공개 파일이 다릅니다.')
        alias_path = '/v4/aliases/' + urlsplit(CONFIG['production_url']).hostname
        alias = json.loads(cli(['api', alias_path, '--raw']))
        if alias.get('projectId') != CONFIG['project']['projectId']:
            raise ContentError('공개 주소가 다른 프로젝트에 연결되어 있습니다.')
        previous = alias['deploymentId']
        status('업로드할 파일 검사')
        dry = json.loads(cli(['deploy', str(folder), '--prod', '--skip-domain', '--yes', '--dry', '--json']))
        if {f['path'] for f in dry['files']} != set(CONFIG['files']) - {'.vercelignore'}:
            raise ContentError('업로드 목록에 예상하지 않은 파일이 있습니다.')
        for f in dry['files']:
            if sha1((folder/f['path']).read_bytes()).hexdigest() != f['sha']:
                raise ContentError('업로드 파일 검증 실패')
        status('새 홈페이지 배포 중')
        result = json.loads(cli(['deploy', str(folder), '--prod', '--skip-domain', '--yes', '--json']))
        # Interactive CLI sessions return the deployment directly; agent sessions
        # wrap it in a status envelope. The local manager supports both formats.
        deployment = result.get('deployment', result)
        if deployment['readyState'] != 'READY': raise ContentError('새 배포가 완료되지 않았습니다.')
        status('공개 주소에 적용 중', deployment_url=deployment['url'])
        for n, h in p['baseline'].items():
            if digest(store.root/n) != h: raise ContentError('배포 중 파일이 바뀌었습니다. 미리보기를 다시 만들어 주세요.')
        current_alias = json.loads(cli(['api', alias_path, '--raw']))
        if current_alias['deploymentId'] != previous:
            raise ContentError('공개 중인 버전이 다른 곳에서 변경됐습니다. 미리보기 후 다시 시도해 주세요.')
        cli(['promote', deployment['url'], '--yes'])
        promoted = True
        status('공개 홈페이지 확인 중')
        verify_runtime(CONFIG['production_url'], folder, job['revision'], store, static=True, expected=p['api_checks'])
        # Keep the public outcome distinct from a local file-sync failure.
        record = dict(revision=job['revision'], at=now(), deployment_url=deployment['url'], deployment_id=deployment['id'])
        atomic_json(store.home / 'published.json', record)
        promoted = False  # Public verification succeeded; local sync must not undo it.
        unsynced = []
        for name in MANAGED:
            try:
                if digest(store.root/name) != p['baseline'][name]:
                    unsynced.append(name); continue
                destination = store.root / name
                temp = destination.with_name(destination.name + '.manager-tmp')
                shutil.copyfile(folder/name, temp); os.replace(temp, destination)
            except OSError: unsynced.append(name)
        job.update(status='success', stage='공개 반영 완료', finished_at=now(), production_url=CONFIG['production_url'])
        if unsynced:
            job.update(stage='공개 반영 완료 — 일부 PC 파일 동기화가 보류됐습니다. 수정본과 공개본은 보관되어 있습니다.', unsynced_files=unsynced)
    except Exception as exc:
        message = str(exc) if isinstance(exc, ContentError) else '공개 반영 중 오류가 발생했습니다. 인터넷 연결을 확인하고 다시 시도해 주세요.'
        if promoted:
            try:
                cli(['promote', previous, '--yes'])
                message += ' 이전 공개본으로 되돌렸습니다.'
            except Exception:
                message += ' 자동 복원이 실패했습니다. Vercel의 배포 이력에서 이전 공개본을 복원해 주세요.'
        job.update(status='failed', stage=message, finished_at=now())
    atomic_json(store.home / 'job.json', job)


if __name__ == '__main__':
    publish_job(Store(home=sys.argv[1]), sys.argv[2])
