"""User searches and source/eligibility boundaries for the official index."""
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from vaccination import catalog, search_vaccination

@pytest.fixture
def client(monkeypatch, public_guidance_contact_db):
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED','1')
    monkeypatch.setenv('DATA_BACKEND','sqlite')
    monkeypatch.setenv('SQLITE_PATH',str(public_guidance_contact_db))
    monkeypatch.setenv('ENABLE_LLM','false')
    monkeypatch.setenv('SMS_MODE','mock')
    import app as application
    monkeypatch.setattr(application.limiter,'enabled',False)
    monkeypatch.setattr(application,'best_effort_log',lambda *a,**k:None)
    return application.app.test_client()

@pytest.mark.parametrize('query,expected',[
    ('독감','V008'), ('인플루엔자','V008'), ('독감접종','V008'),
    ('동탄 독감','V008'), ('코로나19','V010'), ('코로나 백신','V010'),
    ('HPV 남아','V012'), ('HPV남자','V012'), ('2014 남아','V012'),
    ('가다실 9가','V014'), ('B형 간염','V004'), ('비형간염','V004'),
    ('BCG','V003'), ('비씨지','V003'), ('장티푸스','V006'),
    ('대상포진','V011'), ('임산부 백일해','V017'), ('해외여행 황열','V015'),
    ('폐렴','V005'), ('신증후군출혈열','V007'), ('홍역','V016'),
    ('접종기록','V019'), ('피해보상','V020'), ('예방접종 시간','V001'),
])
def test_real_queries_find_topic(query, expected):
    result=search_vaccination(query)
    assert expected in [r['id'] for r in result['guides']]

def test_entire_index_is_reachable_without_duplicates():
    result=search_vaccination('접종')
    assert len(result['guides']) == 20
    for kind,expected in [('sources',932),('facilities',309)]:
        ids=[]
        for page in range(1,(expected+7)//8+1):
            part=search_vaccination('접종',kind=kind,page=page)[kind]
            assert part['total']==expected
            ids.extend(r['id'] for r in part['results'])
        assert len(ids)==len(set(ids))==expected
    assert not search_vaccination('접종',page=1000)['sources']['results']

def test_facility_disease_and_area_constraints():
    result=search_vaccination('동탄 독감')['facilities']
    assert result['total']==120
    for r in result['results']:
        assert '동탄' in r['region']+r['address']
        assert any('독감' in p['name'] and p['as_of']=='2026-09-17' for p in r['programs'])
    assert search_vaccination('대상포진')['facilities']['total']==104
    assert search_vaccination('위탁의료기관')['facilities']['total']==309
    assert search_vaccination('BCG')['facilities']['total']==7
    assert search_vaccination('동탄 BCG')['facilities']['total']==5

def test_unrelated_and_empty_queries_do_not_match():
    for query in ['여권','없는백신xyz','   ','!!!']:
        result=search_vaccination(query)
        assert not result['guides'] and not result['sources']['total'] and not result['facilities']['total']

def test_current_season_does_not_reuse_expired_notice():
    result=search_vaccination('코로나19',today='2026-09-30')
    guide=result['guides'][0]
    assert guide['id']=='V010' and guide['valid_until']=='2027-06-30' and not guide['expired']
    assert any('12세 미만' in line and '별도' in line for line in guide['details'])
    assert all(g['expired'] for g in search_vaccination('코로나19',today='2027-07-01')['guides'])

def test_national_and_city_hpv_are_distinct():
    guides={g['id']:g for g in catalog()['guides']}
    assert '2014' in guides['V012']['summary']
    assert '여성' in guides['V014']['summary']
    assert '6개월 안' in ' '.join(guides['V014']['details'])
    assert guides['V012']['phone'] != guides['V014']['phone']
    assert guides['V015']['review_required']
    assert guides['V017']['review_required']

def test_sources_and_links_are_public_allowlisted_fields():
    data=catalog()
    assert data['coverage']['search_results']==937
    assert len({s['url'] for s in data['sources']})==932
    for record in data['sources']:
        assert set(record)=={'id','title','url','published_date','category','keywords','period_label','related_task_ids'}
        assert urlsplit(record['url']).hostname in {'www.hscity.go.kr','nip.kdca.go.kr'}
        assert '<' not in record['title']
    task_ids={r['id'] for r in json.loads((Path(__file__).resolve().parents[1]/'data/deployment_catalog.json').read_text('utf-8'))['tasks']}
    assert all(set(g['related_task_ids']) <= task_ids for g in data['guides'])
    assert all(p['as_of'] in {'2026-01-02','2026-08-06','2026-09-17','2026-09-30'} for r in data['facilities'] for p in r['programs'])

def test_search_api_keeps_tasks_and_includes_vaccination(client):
    response=client.post('/api/search',json={'query':'HPV 남아'})
    assert response.status_code==200
    body=response.get_json()
    assert body['total']==body['total_count']
    assert body['results']==body['items']
    assert body['vaccination']['guides'][0]['id']=='V012'
    page=client.post('/api/vaccination/search',json={'query':'접종','kind':'sources','page':2,'source_scope':'all'}).get_json()
    assert page['sources']['page']==2 and len(page['sources']['results'])==8

@pytest.mark.parametrize('payload',[[],None,{'query':'x'}, {'query':'접종','page':True},
                                  {'query':'접종','page':0},{'query':'접종','page':1001},
                                  {'query':'접종','kind':'other'}])
def test_vaccination_api_rejects_invalid_paging(client,payload):
    assert client.post('/api/vaccination/search',json=payload).status_code==400
