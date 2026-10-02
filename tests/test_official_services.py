"""Official program coverage, dates, uncertain source text and real API discovery."""
from datetime import date
import json
from pathlib import Path
from urllib.parse import urlsplit
import pytest
from official_services import catalog, search_official_services

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('guide',catalog()['guides'],ids=lambda g:g['id'])
def test_every_reviewed_program_is_discoverable(guide):
    for query in [guide['keywords'][0],guide['title']]:
        found=search_official_services(query)['guides']
        assert guide['id'] in {g['id'] for g in found},query
        assert len(found)==len({g['id'] for g in found})

@pytest.mark.parametrize('query',['폐렴','폐렴 치료','접종','HbA1c','여권 재발급','없는사업xyz','!!!','   '])
def test_no_navigation_or_negative_caution_matches(query):
    assert not search_official_services(query)['guides']

@pytest.mark.parametrize('query',['암진단','암 진단','암진단 지원'])
def test_cancer_diagnosis_finds_existing_cost_support(query):
    assert [g['id'] for g in search_official_services(query)['guides']]==['S031']

def test_end_dates_do_not_stay_open_after_september():
    for query,id in [('난임시술중단','S025'),('난자동결','S026')]:
        before=next(g for g in search_official_services(query,today=date(2026,9,30))['guides'] if g['id']==id)
        after=next(g for g in search_official_services(query,today=date(2026,10,1))['guides'] if g['id']==id)
        assert not before['expired'] and after['expired']
        assert after['valid_until']=='2026-09-30'
    assert '종료 후에도' in ' '.join(next(g for g in catalog()['guides'] if g['id']=='S025')['details'])

def test_every_menu_has_existing_or_new_guide_and_no_same_title_duplicates():
    collections=[catalog(),*[json.loads((ROOT/f'data/{n}.json').read_text('utf-8')) for n in ['examination_guidance','vaccination_guidance']]]
    urls={r['url'] for c in collections for g in c['guides'] for r in g.get('references',g.get('sources',[]))}
    assert all(p['url'] in urls for p in catalog()['evidence'])
    titles=[g['title'] for c in collections for g in c['guides']]
    assert len(titles)==len(set(titles))

def test_task_links_sources_and_public_data_have_no_private_columns():
    ids={t['id'] for t in json.loads((ROOT/'data/deployment_catalog.json').read_text('utf-8'))['tasks']}
    for g in search_official_services('주요사업')['guides']:
        assert set(g['related_task_ids'])<=ids
        assert set(g['related_task_labels'])==set(g['related_task_ids'])
        assert not {'body','source_row','contact_name','author','keywords'} & g.keys()
        assert all(set(c)=={'label','phone'} for c in g['contacts'])
        for r in g['references']:
            assert urlsplit(r['url']).scheme=='https'
            assert urlsplit(r['url']).hostname in {'www.hscity.go.kr','chronic.hscity.go.kr','www.hsmind.or.kr','www.hsalcohol.kr','www.hsmindstep.or.kr'}
    uncertain={g['id']:g['confirmation'] for g in catalog()['guides'] if g['confirmation']}
    assert {'S004','S017','S019','S026','S028','S031','S035','S036','S037'}<=uncertain.keys()
    assert '2,000백만원' in uncertain['S028']
    assert all('2,000백만원' not in s for s in next(g for g in catalog()['guides'] if g['id']=='S028')['details'])
    from public_guidance import load_public_guidance
    public=load_public_guidance()
    for g in catalog()['guides']:
        for task_id,label in g['related_task_labels'].items():
            if task_id in public:assert label==public[task_id]['public_title']
    assert '인바디' not in json.dumps(catalog(),ensure_ascii=False)

def test_api_service_discovery_preserves_task_details(monkeypatch,public_guidance_contact_db):
    monkeypatch.setenv('DATA_BACKEND','sqlite');monkeypatch.setenv('SQLITE_PATH',str(public_guidance_contact_db))
    import app as application
    monkeypatch.setattr(application.limiter,'enabled',False)
    monkeypatch.setattr(application,'best_effort_log',lambda *a,**k:None)
    client=application.app.test_client()
    for query,wanted,linked in [('산후 도우미','S015',{'M004','F109'}),('모바일 헬스케어','S012',set()),('희귀질환','S034',{'M001','F109'}),('휠체어','S009',{'R006','F106'}),('13주 프로그램','S006',{'H002','F201'})]:
        body=client.post('/api/search',json={'query':query,'limit':100}).get_json()
        assert wanted in {g['id'] for g in body['services']['guides']}
        assert linked <= {t['id'] for t in body['items']}
        assert len(body['items'])==len({t['id'] for t in body['items']})
        for t in body['items']:
            assert {k:v for k,v in t.items() if k!='score'}==client.get('/api/tasks/'+t['id']).get_json()

def test_existing_postpartum_detail_and_sms_include_changed_eligibility():
    from public_guidance import load_public_guidance
    guidance=load_public_guidance()['M004']
    assert '모든 출산가정' not in guidance['eligibility']
    assert '150%' in guidance['eligibility'] and '2026년 10월 1일' in guidance['eligibility']
    assert 'eligibility' in guidance['sms_fields']
