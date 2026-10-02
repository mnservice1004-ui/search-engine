"""Regression cases for the user's pneumonia screenshot and unified discovery."""
import pytest
from vaccination import search_vaccination

@pytest.fixture
def client(monkeypatch,public_guidance_contact_db):
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED','1');monkeypatch.setenv('DATA_BACKEND','sqlite')
    monkeypatch.setenv('SMS_MODE','mock');monkeypatch.setenv('SQLITE_PATH',str(public_guidance_contact_db))
    import app as application
    monkeypatch.setattr(application.limiter,'enabled',False)
    monkeypatch.setattr(application,'best_effort_log',lambda *a,**k:None)
    return application.app.test_client()

def test_pneumonia_links_real_tasks_and_preserves_public_detail(client):
    body=client.post('/api/search',json={'query':'폐렴','limit':100}).get_json()
    assert [t['id'] for t in body['results']]==['M009','F109']
    assert body['total']==body['returned_count']==2
    assert [g['id'] for g in body['vaccination']['guides']]==['V005']
    for t in body['results']:
        assert {k:v for k,v in t.items() if k!='score'}==client.get('/api/tasks/'+t['id']).get_json()


@pytest.mark.parametrize('query',['산전검사','산전 검사','산전검진','산전 검사 안내'])
def test_prenatal_search_also_shows_distinct_preconception_checkup(client,query):
    body=client.post('/api/search',json={'query':query,'limit':100}).get_json()
    guides=body['examinations']['guides']
    ids=[g['id'] for g in guides]
    assert set(ids)=={'E022','E031','E032'}
    assert len(ids)==len(set(ids))==3
    before=next(g for g in guides if g['id']=='E022')
    assert '임신 전 검사' in before['title']
    assert before['related_task_ids']==['A002','F104']
    assert before['fee']=='무료'
    for id in ['E031','E032']:
        after=next(g for g in guides if g['id']==id)
        assert '임산부' in after['title']
        assert after['related_task_ids']==['A005','F109']
    task_ids=[t['id'] for t in body['items']]
    assert {'A002','F104','A005','F109'}<=set(task_ids)
    assert len(task_ids)==len(set(task_ids))


@pytest.mark.parametrize('query',[
    '착상 전 검사','착상전검사','임신 전 검사','임신전검사',
    '임신 전 건강검진','신혼부부 건강검진','혼전검사',
])
def test_preconception_queries_link_existing_newlywed_guide_once(client,query):
    guides=client.post('/api/search',json={'query':query}).get_json()['examinations']['guides']
    assert [g['id'] for g in guides]==['E022']


def test_cancer_diagnosis_shows_screening_and_existing_support_without_false_diagnosis(client):
    body=client.post('/api/search',json={'query':'암진단','limit':100}).get_json()
    assert [g['id'] for g in body['examinations']['guides']]==['E033']
    assert [g['id'] for g in body['services']['guides']]==['S031']
    assert not body['vaccination']['guides']
    assert 'R001' in {t['id'] for t in body['items']}
    assert [t['id'] for t in body['items']]==['R001']
    assert '확진을 뜻하지 않으며' in body['examinations']['guides'][0]['caution']
    assert not any(g['id'] in {'E009','E010','E011','E012','E013'} for g in body['examinations']['guides'])
    screening=client.post('/api/search',json={'query':'암검진','limit':100}).get_json()
    assert [g['id'] for g in screening['examinations']['guides']]==['E033']
    assert not screening['services']['guides']
    assert not screening['items']
    for query,expected_exam,expected_service,expected_tasks in [
        ('암 진단',['E033'],['S031'],['R001']),
        ('암 검진',['E033'],[],[]),
        ('암진단 검사',['E033'],[],[]),
        ('암진단 지원',[],['S031'],['R001']),
    ]:
        result=client.post('/api/search',json={'query':query,'limit':100}).get_json()
        assert [g['id'] for g in result['examinations']['guides']]==expected_exam
        assert [g['id'] for g in result['services']['guides']]==expected_service
        assert [t['id'] for t in result['items']]==expected_tasks

@pytest.mark.parametrize('query,ids',[
    ('HbA1c',{'A002','F104'}),('익명 HIV',{'A004','F104'}),
    ('골밀도',{'A019','F102'}),('독감',{'M009','F109'}),
])
def test_guidance_task_relationships_are_searchable_once(client,query,ids):
    body=client.post('/api/search',json={'query':query,'limit':100}).get_json()
    actual=[t['id'] for t in body['results']]
    assert ids<=set(actual) and len(actual)==len(set(actual))
    short=client.post('/api/search',json={'query':query,'limit':1}).get_json()
    assert short['total']==body['total'] and short['results']==body['results'][:1]

def test_pneumonia_does_not_rewrite_other_diseases():
    all_sources=search_vaccination('폐렴',source_scope='all')['sources']
    rows=[]
    for page in range(1,(all_sources['total']+7)//8+1):
        rows += search_vaccination('폐렴',source_scope='all',page=page)['sources']['results']
    assert not any('마이코플라스마' in row['title'] for row in rows)
    for query in ['마이코플라스마 폐렴','폐렴 치료','폐렴 증상']:
        assert not search_vaccination(query)['guides']

def test_official_pages_and_archive_are_disjoint_and_complete():
    def ids(scope):
        total=search_vaccination('접종',source_scope=scope)['sources']['total']
        return {r['id'] for page in range(1,(total+7)//8+1)
                for r in search_vaccination('접종',source_scope=scope,page=page)['sources']['results']}
    current,archive=ids('current'),ids('archive')
    assert len(current)==14 and len(archive)==918
    assert not current&archive and len(current|archive)==932
    for r in search_vaccination('폐렴',source_scope='current')['sources']['results']:
        assert r['published_date'] is None and r['category']!='행정·채용'

def test_default_region_is_explicit_and_region_paging_stays_scoped(client):
    body=client.post('/api/search',json={'query':'폐렴'}).get_json()['vaccination']
    assert body['region']=='dongtan' and body['source_scope']=='current'
    assert body['facility_counts']=={'dongtan':85,'all':211}
    assert body['facilities']['total']==85
    seen=[]
    for page in range(1,12):
        data=client.post('/api/vaccination/search',json={'query':'폐렴','kind':'facilities','region':'dongtan','page':page}).get_json()
        assert data['facilities']['total']==85
        assert all('동탄' in f['region'] for f in data['facilities']['results'])
        seen += [f['id'] for f in data['facilities']['results']]
    assert len(seen)==len(set(seen))==85
    all_regions=client.post('/api/vaccination/search',json={'query':'폐렴','kind':'facilities','region':'all'}).get_json()
    assert all_regions['facilities']['total']==211

@pytest.mark.parametrize('options',[{'region':'bad'},{'source_scope':'bad'},{'region':None}])
def test_invalid_scope_is_rejected(client,options):
    assert client.post('/api/vaccination/search',json={'query':'폐렴',**options}).status_code==400
