"""Operator workflows: drafts, concurrent edits, recovery and publication gates."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import json
from unittest.mock import Mock
from zipfile import ZipFile, ZIP_DEFLATED
import pytest

from admin.content_store import Store, ContentError, FILES, ROOT, digest, read_json, validate, replace_phone, atomic_json
from admin import publishing

@pytest.fixture
def store(tmp_path):
    s = Store(home=tmp_path/'manager')
    s.initialize()
    return s

def test_draft_save_conflict_and_restore_do_not_touch_live_files(store):
    before = {n:digest(ROOT/n) for n in [*FILES.values(),'data/health_search.db'] if (ROOT/n).exists()}
    initial = store.read(); payload = deepcopy(initial['payload'])
    payload['data']['examinations']['guides'][21]['keywords'].append('시험검색어')
    revision = store.save(payload, initial['id'], '검색어 변경')
    assert store.read()['id'] == revision
    with pytest.raises(ContentError, match='다른 창'):
        store.save(payload, initial['id'], '오래된 창에서 저장')
    restored = store.restore(initial['id'], revision)
    assert restored != initial['id']
    assert store.read()['payload'] == initial['payload']
    assert before == {n:digest(ROOT/n) for n in before}

def test_invalid_dates_duplicate_contacts_and_missing_task_rejected(store):
    initial = store.read()
    bad = deepcopy(initial['payload'])
    bad['data']['plans']['items'][0]['period'] = {'start':'2026-11-30','end':'2026-11-01'}
    with pytest.raises(ContentError, match='종료일'): store.save(bad, initial['id'], 'bad')
    bad = deepcopy(initial['payload'])
    bad['data']['catalog']['contacts'].append(deepcopy(bad['data']['catalog']['contacts'][0]))
    with pytest.raises(ContentError, match='중복'): validate(bad)
    bad = deepcopy(initial['payload'])
    bad['data']['services']['guides'][0]['related_task_ids'] = ['Z999']
    with pytest.raises(ContentError, match='존재'): validate(bad)
    assert store.read()['id'] == initial['id']

def test_backup_round_trip_and_corrupted_asset_rejected(store):
    initial = store.read(); backup = store.backup()
    with ZipFile(BytesIO(backup)) as archive:
        assert set(archive.namelist()) == {'content.json', *{'assets/'+p['asset'] for p in initial['payload']['photos']}}
    payload = deepcopy(initial['payload']); payload['data']['plans']['items'][0]['title'] = '변경한 일정'
    updated = store.save(payload,initial['id'],'일정 변경')
    store.import_backup(backup,updated)
    assert store.read()['payload'] == initial['payload']
    corrupt = BytesIO()
    with ZipFile(BytesIO(backup)) as original, ZipFile(corrupt,'w',ZIP_DEFLATED) as archive:
        for name in original.namelist(): archive.writestr(name, original.read(name) if name=='content.json' else b'invalid')
    with pytest.raises(ContentError, match='검증'): store.import_backup(corrupt.getvalue(),store.read()['id'])

def test_phone_replace_updates_all_repeated_contact_fields(store):
    payload = store.read()['payload']
    count = replace_phone(payload,'031-5189-4369','031-5189-4999')
    assert count > 2
    assert '031-5189-4369' not in json.dumps(payload['data'],ensure_ascii=False)
    validate(payload)

def test_preview_bundle_has_only_allowed_files_and_preserves_photo_metadata(store,tmp_path):
    record = store.read(); folder=tmp_path/'runtime'
    publishing.make_bundle(store,record['id'],folder)
    actual={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    assert actual == set(publishing.CONFIG['files']) | {'.vercel/project.json'}
    assert not any('admin/' in p or p.endswith('.db') or '.env' in p for p in actual)
    assert (folder/'public/index.html').read_text('utf-8') == (ROOT/'public/index.html').read_text('utf-8')
    assert all(digest(folder/n)==digest(ROOT/n) for n in publishing.PHOTO_PATHS)

@pytest.mark.parametrize('kind,module_name,query',[('examinations','examinations','산전검사'),('services','official_services','진료'),('vaccination','vaccination','접종')])
def test_hidden_guides_cannot_be_forced_back_by_menu_mapping(store,monkeypatch,kind,module_name,query):
    import importlib
    module=importlib.import_module(module_name)
    data=store.read()['payload']['data'][kind]
    hidden={g['id'] for g in data['guides']}
    for g in data['guides']: g['active']=False
    monkeypatch.setattr(module,'catalog',lambda:data)
    search={'examinations':module.__dict__.get('search_examinations'),
            'services':module.__dict__.get('search_official_services'),
            'vaccination':module.__dict__.get('search_vaccination')}[kind]
    assert search(query,include_ids=hidden)['guides']==[]

def test_publication_requires_latest_preview_and_blocks_changed_source(store,monkeypatch):
    record=store.read()
    atomic_json(store.home/'preview.json',dict(id='preview',revision=record['id'],baseline={'app.py':'wrong'},hashes={}))
    atomic_json(store.home/'job.json',dict(id='job',revision=record['id'],preview_id='preview'))
    call=Mock(); monkeypatch.setattr(publishing,'cli',call)
    publishing.publish_job(store,'job')
    assert read_json(store.home/'job.json')['status']=='failed'
    call.assert_not_called()
    with pytest.raises(ContentError,match='최신'):
        publishing.start_publish(store,'stale','preview')

@pytest.mark.parametrize('wrapped', [True, False])
def test_failed_public_verification_promotes_previous_release(store,tmp_path,monkeypatch,wrapped):
    record=store.read(); folder=tmp_path/'runtime'
    baseline=publishing.make_bundle(store,record['id'],folder)
    hashes={n:digest(folder/n) for n in publishing.CONFIG['files']}
    atomic_json(store.home/'preview.json',dict(id='preview',revision=record['id'],baseline=baseline,hashes=hashes,api_checks={}))
    atomic_json(store.home/'job.json',dict(id='job',revision=record['id'],preview_id='preview'))
    original_published=read_json(store.home/'published.json')
    calls=[]
    def cli(args):
        calls.append(args)
        if args[0]=='api': return json.dumps({'projectId':publishing.CONFIG['project']['projectId'],'deploymentId':'previous-deployment'})
        if '--dry' in args:
            from hashlib import sha1
            runtime=Path(args[1])
            return json.dumps({'files':[{'path':n,'sha':sha1((runtime/n).read_bytes()).hexdigest()} for n in publishing.CONFIG['files'] if n!='.vercelignore']})
        if args[0]=='deploy':
            deployment = {'id':'test','url':'https://test.invalid','readyState':'READY'}
            return json.dumps({'deployment':deployment} if wrapped else deployment)
        return ''
    monkeypatch.setattr(publishing,'cli',cli)
    monkeypatch.setattr(publishing,'verify_runtime',Mock(side_effect=ContentError('검증 실패')))
    publishing.publish_job(store,'job')
    assert read_json(store.home/'job.json')['status']=='failed'
    assert calls[-1] == ['promote','previous-deployment','--yes']
    assert read_json(store.home/'published.json')==original_published
    assert all(digest(ROOT/n)==h for n,h in baseline.items())

def test_manager_pages_and_real_form_save(monkeypatch,tmp_path):
    from streamlit import config
    from streamlit.testing.v1 import AppTest
    config.get_config_options(force_reparse=True,options_from_flags={'server.address':'127.0.0.1'})
    monkeypatch.setenv('HEALTH_MANAGER_HOME',str(tmp_path/'ui'))
    app=AppTest.from_file(str(ROOT/'admin/dashboard.py'),default_timeout=25).run()
    assert not app.exception
    for page in ['tasks','guides','plans','photos','publish','history']:
        app.switch_page('app_pages/'+page+'.py').run(timeout=25)
        assert not app.exception, page
    app.switch_page('app_pages/guides.py').run()
    app.selectbox[0].select('examinations').run()
    app.selectbox[1].select('E022').run()
    field=next(t for t in app.text_area if t.label.startswith('검색어'))
    field.set_value(field.value+'\n테스트용검색어')
    next(b for b in app.button if b.label=='수정본 저장').click().run()
    assert not app.exception
    saved=Store(home=tmp_path/'ui').read()['payload']
    assert '테스트용검색어' in next(g for g in saved['data']['examinations']['guides'] if g['id']=='E022')['keywords']
