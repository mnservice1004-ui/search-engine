import json
from pathlib import Path
import shutil
import subprocess
import pytest
from official_services import catalog,menu_guide_ids

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def client(monkeypatch,public_guidance_contact_db):
    monkeypatch.setenv('DATA_BACKEND','sqlite')
    monkeypatch.setenv('SQLITE_PATH',str(public_guidance_contact_db))
    import app as application
    monkeypatch.setattr(application.limiter,'enabled',False)
    monkeypatch.setattr(application,'best_effort_log',lambda *a,**k:None)
    return application.app.test_client()

@pytest.mark.parametrize('menu',[m for m in catalog()['menu_index'] if m['guide_ids']],ids=lambda m:m['title'])
def test_each_official_menu_resolves_to_existing_guides_once(client,menu):
    body=client.post('/api/search',json={'query':menu['title'],'limit':100}).get_json()
    ids=[g['id'] for kind in ['services','vaccination','examinations'] for g in body[kind]['guides']]
    assert set(menu['guide_ids'])<=set(ids)
    assert len(ids)==len(set(ids))

def test_all_homepage_menus_have_an_explicit_disposition():
    menus=catalog()['menu_index']
    assert len(menus)==81 and len({m['url'] for m in menus})==81
    assert len([m for m in menus if m['guide_ids']])==65
    assert all(m['guide_ids'] or m['task_ids'] or m.get('note') for m in menus)
    assert 'S013' in menu_guide_ids('AI·IoT기반 어르신 건강관리사업')
    assert not menu_guide_ids('없는사업xyz')

def test_supplements_reuse_existing_programs_and_do_not_include_private_columns():
    guides={g['id']:g for g in catalog()['guides']}
    assert len(guides)==47
    assert len([g for g in guides.values() if any('AIhealthcare.jsp' in r['url'] for r in g['references'])])==1
    assert guides['S013']['related_task_ids']==['R002']
    assert '6개월' in ' '.join(guides['S013']['details'])
    assert 'S046' in menu_guide_ids('산후조리원')
    assert '확인' in guides['S046']['confirmation']
    assert all(set(c)=={'label','phone'} for g in guides.values() for c in g['contacts'])

def test_browser_card_composition():
    result=subprocess.run([shutil.which('node'),'--test','tests/service_guidance_composition.cjs'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stdout+result.stderr
