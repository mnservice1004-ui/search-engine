"""Public examination guidance matched to existing permanent service records."""
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata

DATA_PATH = Path(__file__).resolve().parent / 'data/examination_guidance.json'
ALIASES = {'혈액':('혈액','피검사'), '공복':('공복','금식'), 'HIV':('hiv','에이즈'),
           'X선':('x선','x-ray','xray','엑스레이','엑스선'), '골밀도':('골밀도','골다공증'),
           '성병':('성병','성매개감염병'), '임산부':('임산부','임신부'),
           'B형간염':('b형간염','비형간염'), 'A형간염':('a형간염','에이형간염'),
           'C형간염':('c형간염','씨형간염'), '당화혈색소':('hba1c','당화혈색소'),
           'CA199':('ca19-9','ca199'), 'TSH':('tsh',), 'FreeT4':('free t4','freet4'),
           'TotalT3':('total t3','totalt3'), '소변':('소변','요검사'),
           '신혼':('신혼','혼전','예비부부'), '가임력':('가임력','임신준비'),
           '임신전':('임신전','착상전')}

def normalize(value):
    return re.sub(r'[^0-9a-z가-힣]','',unicodedata.normalize('NFKC',str(value)).lower())

def canonical(value):
    value=normalize(value)
    pairs=sorted([(normalize(a),normalize(k)) for k,aliases in ALIASES.items() for a in aliases],key=lambda p:len(p[0]),reverse=True)
    lookup=dict(pairs)
    return re.sub('|'.join(re.escape(a) for a,_ in pairs),lambda m:lookup[m[0]],value)

@lru_cache(maxsize=1)
def catalog():
    data=json.loads(DATA_PATH.read_text('utf-8'))
    assert data['schema_version']==1
    return data

def search_examinations(query, *, include_ids=()):
    data=catalog()
    normalized=normalize(query)
    generic=normalized in {'검사','검진','건강검진','각종검사','검사종류','검사항목','검사안내','검사비용','검사수수료','검사가격','검사준비물','검사결과','검사시간'}
    value=re.sub(r'암\s+진단', '암진단', unicodedata.normalize('NFKC',query).lower())
    # Keep the cancer subject when removing the generic word "검진" below.
    value=re.sub(r'(?<!국가)암\s*검진', '국가암검진', value)
    # Join multi-part test names before removing generic request words.
    pairs=sorted([(a,k) for k,aliases in ALIASES.items() for a in aliases],key=lambda p:len(p[0]),reverse=True)
    pattern='|'.join('\\s*'.join(map(re.escape,a)) for a,_ in pairs)
    lookup={normalize(a):normalize(k) for a,k in pairs}
    value=re.sub(pattern,lambda m:' '+lookup[normalize(m[0])]+' ',value)
    value=re.sub(r'(검사|검진|비용|가격|얼마인가요|얼마예요|얼마|수수료|준비물|처리기간|보건소|화성시|화성|동탄|관련|정보|안내|알려주세요|알려줘|해주세요|받고싶어요|받고싶어|받을수있나요|받나요|하나요|해요|어디서|어디)', ' ',value)
    needles=[canonical(w) for w in re.findall(r'[0-9a-z가-힣]+',value) if len(w)>=2]
    if not needles and not generic and not include_ids:
        return dict(checked_on=data['checked_on'],total=0,guides=[],preparation=[])
    matched=[]
    for item in data['guides']:
        if item.get('active', True) is False: continue
        title=canonical(item['title'])
        haystack=title+canonical(' '.join(item['keywords'])+item['summary'])
        # Negative cautions and missing-field notices must not create matches.
        if '무료' in needles and '무료' not in item['fee']:continue
        terms=[n for n in needles if n!='무료']
        if item['id'] not in include_ids and not generic and (not needles or not all(n in haystack for n in terms)):continue
        score=sum(10 if n in title else 1 for n in terms)
        public={k:item[k] for k in ('id','title','summary','details','fee','result_time','related_task_ids','references','contacts','caution','confirmation','general_preparation')}
        matched.append((score,public))
    matched.sort(key=lambda pair:-pair[0])
    guides=[item for _,item in matched]
    return dict(checked_on=data['checked_on'],total=len(guides),guides=guides,
                preparation=data['preparation'] if any(g['general_preparation'] for g in guides) else [])
