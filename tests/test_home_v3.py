"""Homepage entries resolve to their real existing guides, not empty category pages."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import pytest

ROOT = Path(__file__).resolve().parents[1]
class Homepage(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.ids=[]
        self.feed((ROOT/'public/index.html').read_text('utf-8'))
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.append(attrs['id'])
        if 'data-portal-query' in attrs:self.links.append(attrs)

EXPECTED = {
    '일반진료':'S001','검사':'E001','암검진':'E033','건강진단결과서 발급':'A003',
    '접종':'V001','폐렴':'V005','결핵':'E027','감염병':'S019',
    '임신사전건강관리':'E039','산후도우미':'S015','난임':'S024','영유아':'V002',
    '건강생활실천':'S005','영양플러스':'S011','금연':'S007','구강':'S004','만성질환':'S006',
    '치매':'E040','방문보건':'S013','정신건강':'S042','재활':'S009',
    '암진단 지원':'S031','희귀질환':'S034','의료기관찾기':'S045','의약무':'A017',
}

@pytest.fixture
def client(monkeypatch, public_guidance_contact_db):
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED','1')
    monkeypatch.setenv('DATA_BACKEND','sqlite')
    monkeypatch.setenv('SMS_MODE','mock')
    monkeypatch.setenv('SQLITE_PATH',str(public_guidance_contact_db))
    import app as application
    monkeypatch.setattr(application.limiter,'enabled',False)
    monkeypatch.setattr(application,'best_effort_log',lambda *a,**k:None)
    return application.app.test_client()

def test_homepage_directory_links_match_search_query_and_remain_unique():
    home=Homepage()
    assert len(home.ids)==len(set(home.ids))
    assert len(home.links)==len(EXPECTED)==25
    assert {a['data-portal-query'] for a in home.links}==set(EXPECTED)
    for a in home.links:
        assert parse_qs(urlsplit(a['href']).query)=={'q':[a['data-portal-query']]}

@pytest.mark.parametrize('query,expected',EXPECTED.items())
def test_each_homepage_entry_reaches_its_existing_guidance(client,query,expected):
    response=client.post('/api/search',json={'query':query,'limit':100})
    assert response.status_code==200
    body=response.get_json()
    ids=[x['id'] for x in body['results']]
    for group in ('services','examinations','vaccination'):
        ids += [x['id'] for x in body[group]['guides']]
    assert expected in ids
    assert len(ids)==len(set(ids))
    if query=='암검진':assert not {'E009','E010','E011','E012','E013'} & set(ids)

def test_homepage_retains_dialogs_and_accessible_mobile_menu():
    source=(ROOT/'public/index.html').read_text('utf-8')
    assert 'aria-controls="portal-navigation"' in source
    assert 'aria-expanded="false"' in source
    before=(ROOT/'public/qa/home-modified-a.html').read_text('utf-8')
    for name in ['detail-dialog','sms-dialog','sms-result-dialog']:
        assert f'id="{name}"' in source and f'id="{name}"' in before
    for name in ['query','search-button','health-services','visit-guide','monthly-discovery']:
        assert f'id="{name}"' in source
