"""Reviewed official programs, with explicit task links and Korea-local dates."""
from datetime import datetime
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata
from zoneinfo import ZoneInfo

DATA_PATH = Path(__file__).resolve().parent / 'data/official_services.json'

def normalize(value):
    return re.sub(r'[^0-9a-z가-힣]', '', unicodedata.normalize('NFKC', value).lower())

@lru_cache(maxsize=1)
def catalog():
    data = json.loads(DATA_PATH.read_text('utf-8'))
    if data['schema_version'] != 1:
        raise ValueError('Unsupported official service catalog')
    return data

def menu_guide_ids(query):
    """Exact official menu names resolve to reviewed records, never new cards."""
    key = normalize(query)
    return {id for row in catalog().get('menu_index', [])
            if key in {normalize(row['title']), *map(normalize, row.get('aliases', []))}
            for id in row['guide_ids']}

def search_official_services(query, *, today=None, include_ids=()):
    data = catalog()
    today = today or datetime.now(ZoneInfo('Asia/Seoul')).date()
    value = re.sub(r'암\s+진단', '암진단', unicodedata.normalize('NFKC', query).lower())
    generic = normalize(value) in {'사업', '보건사업', '보건소사업', '주요업무', '주요사업', '사업안내'}
    # Only affirmative subjects are indexed. Eligibility exclusions, disclaimers,
    # shared navigation, contact labels and other programs' names cannot match.
    value = re.sub(r'화성시|화성|동탄구보건소|동탄보건소|보건소|동탄구|동탄|알려주세요|알려줘|해주세요|받고싶어요|관련|문의|안내|신청방법|신청|방법|준비물|서류|비용|얼마예요|어디서', ' ', value)
    terms = [normalize(t) for t in value.split() if len(normalize(t)) >= 2]
    if not terms and not generic and not include_ids:
        return dict(checked_on=data['checked_on'],total=0,guides=[])
    ranked = []
    for item in data['guides']:
        if item.get('active', True) is False: continue
        title = normalize(item['title'])
        subjects = title + normalize(' '.join(item['keywords']) + item['summary'])
        if item['id'] not in include_ids and not generic and (not terms or not all(term in subjects for term in terms)):
            continue
        public = {k:v for k,v in item.items() if k not in {'keywords', 'active'}}
        public['expired'] = bool(item['valid_until'] and today.isoformat() > item['valid_until'])
        ranked.append((public['expired'], -sum(10 if t in title else 1 for t in terms), public))
    ranked.sort(key=lambda row:row[:2])
    guides = [row[2] for row in ranked]
    return dict(checked_on=data['checked_on'],total=len(guides),guides=guides)
