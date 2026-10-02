"""Queries residents actually use, with fees and program boundaries."""
import json
from pathlib import Path
from urllib.parse import urlsplit
import pytest
from examinations import catalog, search_examinations

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('query,expected',[
    ('성인병 검사','E001'),('간기능검사','E001'),('통풍 검사','E001'),('BUN','E001'),
    ('신장기능 검사','E001'),('임산부 풍진','E031'),('임산부 요단백','E032'),
    ('LDL 검사 비용','E002'),('고지혈증 금식','E002'),('HbA1c','E003'),('당화혈색소','E003'),
    ('갑상선검사 얼마인가요','E008'),('피검사 어디서 해요','E001'),
    ('빈혈 검사','E004'),('영유아 빈혈','E005'),('소변 검사','E006'),('요단백 검사','E006'),
    ('소변현미경','E007'),('TSH 검사','E008'),('Free T4','E008'),
    ('AFP','E009'),('CA125','E010'),('CA 19-9 검사','E011'),('CEA','E012'),('PSA','E013'),
    ('A형간염 항체','E014'),('B형 간염 검사','E015'),('C형간염 검사','E016'),('풍진','E017'),
    ('매독 RPR','E018'),('HIV 실명','E019'),('흉부 엑스레이','E020'),('혈액형','E021'),
    ('신혼부부 검진','E022'),('혼전검사','E022'),('성병그린검진','E023'),('골밀도 예약','E024'),
    ('익명 에이즈 검사','E025'),('임질 치료','E026'),('잠복결핵','E027'),('보건증','E028'),
    ('건강진단서','E029'),('외국인 결핵','E030'),('임신부 초기 검사','E031'),('임산부 막달 검사','E032'),
    ('국가암검진','E033'),('암검진','E033'),('암 검진','E033'),('암진단','E033'),('암 진단','E033'),('암진단 검사','E033'),('일반건강검진','E034'),('난청 검사','E035'),('선천성대사이상','E036'),
    ('발달 정밀검사','E037'),('태아 기형아','E038'),('AMH 검사','E039'),('정액검사','E039'),('치매검사','E040'),
])
def test_resident_queries(query,expected):
    assert expected in [g['id'] for g in search_examinations(query)['guides']]

def test_complete_main_table_coverage_and_distinct_prices():
    data=catalog(); guides={g['id']:g for g in data['guides']}
    assert len(data['guides'])==len(guides)==40
    assert data['coverage']==dict(official_pages=13,main_fee_items=21,main_free_or_radiology_programs=3,related_guides=16,duplicate_xray_merged=True,adult_bundle_rows=6)
    expected=[('5,000원','1주'),('6,100원','1주'),('7,050원','1주'),('4,700원','1주'),('940원','당일'),('1,020원','당일'),('940원','당일'),('10,000원','1주'),*[('5,000원','1주')]*5,('14,160원','1주'),('7,000원','1주'),('6,000원','1주'),('40,050원','1주'),('무료','1주'),('무료','1주'),('6,150원','3일'),('4,070원','1일')]
    assert [(g['fee'],g['result_time']) for g in data['guides'][:21]]==expected
    assert len(search_examinations('검사')['guides'])==40
    assert len(search_examinations('검사 비용')['guides'])==40
    assert [g['id'] for g in search_examinations('8시간')['guides']]==['E001','E002']
    assert 'E003' not in [g['id'] for g in search_examinations('공복')['guides']]
    assert '구성 검사 각각' in ' '.join(guides['E001']['details'])
    assert '2,000' in guides['E030']['fee'] and '6,150' in guides['E020']['fee']

def test_no_false_free_and_no_generic_preparation_for_anonymous_hiv():
    for g in search_examinations('무료 검사')['guides']:assert '무료' in g['fee']
    anon=search_examinations('익명 HIV')
    assert [g['id'] for g in anon['guides']]==['E025']
    assert not anon['preparation'] and not anon['guides'][0]['general_preparation']
    assert not next(g for g in catalog()['guides'] if g['id']=='E030')['general_preparation']

def test_explicit_uncertainties_and_cancer_caution():
    guides={g['id']:g for g in catalog()['guides']}
    assert {g['id'] for g in guides.values() if g['confirmation']}=={'E022','E023','E034','E037','E038','E040'}
    assert '2025년' in guides['E038']['title'] and '2026년' in guides['E038']['confirmation']
    for num in range(9,14):assert '확진검사가 아니며' in guides[f'E{num:03}']['caution']
    assert '소급 지원 불가' in ' '.join(guides['E039']['details'])
    assert '등록기준지' in ' '.join(guides['E023']['details'])

def test_source_links_contact_mappings_and_public_allowlist():
    ids={t['id'] for t in json.loads((ROOT/'data/deployment_catalog.json').read_text('utf-8'))['tasks']}
    refs=set()
    for g in search_examinations('검사')['guides']:
        assert set(g)=={'id','title','summary','details','fee','result_time','related_task_ids','references','contacts','caution','confirmation','general_preparation'}
        assert set(g['related_task_ids'])<=ids
        for r in g['references']:
            assert urlsplit(r['url']).scheme=='https' and urlsplit(r['url']).hostname=='www.hscity.go.kr'
            refs.add(r['url'])
        assert all(set(c)=={'label','phone'} for c in g['contacts'])
    assert len(refs)==14

@pytest.mark.parametrize('query',['접종','없는검사xyz','   ','!!!','여권 재발급'])
def test_unrelated_queries(query):
    assert search_examinations(query)['total']==0

def test_api_retains_task_search_and_adds_guidance(monkeypatch,public_guidance_contact_db):
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED','1');monkeypatch.setenv('DATA_BACKEND','sqlite')
    monkeypatch.setenv('SQLITE_PATH',str(public_guidance_contact_db));monkeypatch.setenv('SMS_MODE','mock')
    import app as application
    monkeypatch.setattr(application.limiter,'enabled',False)
    monkeypatch.setattr(application,'best_effort_log',lambda *a,**k:None)
    client=application.app.test_client()
    result=client.post('/api/search',json={'query':'LDL 검사 비용'}).get_json()
    assert result['examinations']['guides'][0]['id']=='E002'
    assert result['items']==result['results']
    assert result['returned_count']==len(result['results'])
    for id in result['examinations']['guides'][0]['related_task_ids']:
        assert client.get('/api/tasks/'+id).status_code==200
    assert sum(client.post('/api/search',json={'query':'접종'}).get_json()['vaccination']['source_counts'].values())==932
