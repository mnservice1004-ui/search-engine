"""Source-linked vaccination search, independent of permanent task records."""
from datetime import datetime
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata
from zoneinfo import ZoneInfo

DATA_PATH = Path(__file__).resolve().parent / 'data/vaccination_guidance.json'
PAGE_SIZE = 8
ALIASES = {
    '인플루엔자': ('인플루엔자', '인플루엔쟈', '독감'),
    '코로나19': ('코로나19', '코로나', 'covid19', 'covid'),
    'HPV': ('hpv', '사람유두종바이러스', '자궁경부암'),
    '가다실9가': ('가다실9가', '가다실9', 'hpv9가'),
    '가다실4가': ('가다실4가', '가다실4', 'hpv4가'),
    'BCG': ('bcg', '비씨지'), 'B형간염': ('b형간염', '비형간염'),
    '폐렴구균': ('폐렴구균',), '임신부': ('임신부', '임산부'),
    '남아': ('남아', '남자', '남성'), '어르신': ('어르신', '노인'), 'MMR': ('mmr', '홍역'),
}

def normalize(value):
    value = unicodedata.normalize('NFKC', str(value)).lower()
    return re.sub(r'[^0-9a-z가-힣]', '', value)

def tokens(query):
    value = unicodedata.normalize('NFKC', query).lower()
    # Only an unqualified lay query is a shortcut to pneumococcal vaccination.
    # Other pneumonia (e.g. Mycoplasma) is not a synonym for pneumococcus.
    if re.fullmatch(r'(?:동탄(?:구)?|화성(?:시)?)?폐렴(?:예방접종|접종|백신|주사)?', normalize(query)):
        value = value.replace('폐렴', '폐렴구균')
    pairs = [(alias, key) for key, aliases in ALIASES.items() for alias in aliases]
    # Single-pass replacement prevents a canonical form being replaced twice.
    pattern = '|'.join('\\s*'.join(map(re.escape, a)) for a,_ in sorted(pairs,key=lambda p:len(p[0]),reverse=True))
    lookup = {normalize(a):normalize(k) for a,k in pairs}
    value = re.sub(pattern, lambda m:' '+lookup[normalize(m[0])]+' ', value)
    ignored = {'접종','예방접종','백신','관련','안내','정보','어디서','어디','맞나요','알려줘','주세요'}
    return [w for w in re.findall(r'[0-9a-z가-힣]+',value) if len(w)>=2 and w not in ignored]

@lru_cache(maxsize=8192)
def searchable(value):
    text = normalize(value)
    for key, aliases in ALIASES.items():
        if any(normalize(a) in text for a in aliases): text += normalize(key)
    return text

@lru_cache(maxsize=1)
def catalog():
    data = json.loads(DATA_PATH.read_text('utf-8'))
    assert data['schema_version'] == 1
    return data

def _page(items, page):
    return {'total':len(items),'page':page,'page_size':PAGE_SIZE,
            'results':items[(page-1)*PAGE_SIZE:page*PAGE_SIZE]}

def search_vaccination(query, *, kind='sources', page=1, today=None, region='all', source_scope='all', include_ids=()):
    data = catalog(); needles = tokens(query)
    generic = normalize(query) in {'접종','예방접종','백신','예방주사'}
    if not needles and not generic and not include_ids:
        return {'checked_on':data['checked_on'],'guides':[],'sources':_page([],1),'facilities':_page([],1),
                'source_counts':{'current':0,'archive':0},'facility_counts':{'dongtan':0,'all':0},
                'region':region,'source_scope':source_scope}
    def score(title, extra):
        title = searchable(title); haystack = title + searchable(extra)
        if not generic and not all(n in haystack for n in needles): return 0
        return 1 + sum(10 if n in title else 1 for n in needles)
    now = today or datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    guides=[]; sources=[]; facilities=[]
    for record in data['guides']:
        rank=score(record['title'],' '.join(record['keywords'])+' 화성 동탄 보건소 '+record['summary'])
        if rank or record['id'] in include_ids:
            public = {k:v for k,v in record.items() if k not in {'keywords','review_required'}}
            public.update(needs_confirmation=record['review_required'], expired=bool(record['valid_until'] and record['valid_until']<now))
            guides.append((rank,public))
    guides.sort(key=lambda p:(p[1]['expired'],-p[0],p[1]['id']))
    source_counts={'current':0,'archive':0}
    for record in data['sources']:
        rank=score(record['title'],' '.join(record['keywords'])+' '+(record['published_date'] or ''))
        # Dated notices remain dated reference material; they do not establish
        # that a program still runs. Current guidance is curated separately.
        archived = bool(record['published_date']) or record['category']=='행정·채용'
        if rank: source_counts['archive' if archived else 'current'] += 1
        if rank and (source_scope=='all' or (source_scope=='archive')==archived):
            sources.append((rank,record))
    sources.sort(key=lambda p:(p[0],p[1]['category']!='행정·채용',p[1]['published_date'] or '9999'),reverse=True)
    facility_counts={'dongtan':0,'all':0}
    for record in data['facilities']:
        rank=score(record['title'],'위탁의료기관 병원 의원 '+record['region']+' '+record['address']+' '+record['phone']+' '+' '.join(p['name'] for p in record['programs']))
        if rank:
            facility_counts['all'] += 1
            if '동탄' in record['region']: facility_counts['dongtan'] += 1
            if region=='dongtan' and '동탄' not in record['region']: continue
            public = {k:v for k,v in record.items() if k!='programs'}
            public['programs'] = [{'name':p['name'],'as_of':p['as_of'],'reference':p['source'],
                                   'phone':p.get('phone')} for p in record['programs']]
            facilities.append((rank,public))
    facilities.sort(key=lambda p:(-p[0],p[1]['title']))
    return {'checked_on':data['checked_on'],'guides':[v for _,v in guides],
            'source_counts':source_counts,'facility_counts':facility_counts,'region':region,'source_scope':source_scope,
            'sources':_page([v for _,v in sources],page if kind=='sources' else 1),
            'facilities':_page([v for _,v in facilities],page if kind=='facilities' else 1)}
