"""Versioned public-content drafts. Never opens the private operating database."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, date
from hashlib import sha256
from io import BytesIO
import html
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    'catalog': 'data/deployment_catalog.json',
    'tasks': 'data/public_guidance.json',
    'examinations': 'data/examination_guidance.json',
    'services': 'data/official_services.json',
    'vaccination': 'data/vaccination_guidance.json',
    'plans': 'public/data/monthly-plan-2026-10.json',
}
PHOTO_PATHS = ['public/images/hero-building-v2.png', *[
    f'public/images/hero-photo-{i}.jpg' for i in range(1, 4)]]
PHOTO_CAPTIONS = ['우리 동네 건강의 시작', '방문을 맞이하는 정문', '로비와 민원실', '복도와 층별 안내']
GUIDE_KINDS = ('examinations', 'services', 'vaccination')
GUIDE_FIELDS = {
    'examinations': {'id','title','summary','keywords','details','related_task_ids','caution','confirmation','contacts','fee','result_time','references','general_preparation','locator'},
    'services': {'id','title','summary','keywords','details','related_task_ids','caution','confirmation','contacts','fee','result_time','references','valid_until','related_task_labels','result_category'},
    'vaccination': {'id','title','summary','keywords','details','related_task_ids','caution','checked_on','phone','review_required','sources','valid_until'},
}
OFFICIAL_HOSTS = {'www.hscity.go.kr', 'chronic.hscity.go.kr', 'nip.kdca.go.kr',
    'nqs.kdca.go.kr', 'www.kdca.go.kr', 'hsmind.or.kr', 'www.hsmind.or.kr',
    'www.hsalcohol.kr', 'www.hsmindstep.or.kr'}


class ContentError(ValueError):
    pass


def now():
    return datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds')


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        with temp.open('w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path):
    return json.loads(Path(path).read_text('utf-8'))


def text(value, label, required=False, limit=12000):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ContentError(f'{label}: 내용을 확인해 주세요.')
    if '\x00' in value:
        raise ContentError(f'{label}: 사용할 수 없는 문자가 있습니다.')


def phone(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:0\d{8,10}|1\d{2,7})', re.sub(r'[\s()-]', '', value)):
        raise ContentError('전화번호 형식을 확인해 주세요. 예: 031-5189-4370')


def date_value(value, label, optional=False):
    if optional and value in ('', None):
        return
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ContentError(f'{label}: 날짜는 YYYY-MM-DD 형식으로 입력해 주세요.') from None


def rows_unique(rows, key, label):
    ids = [r.get(key) for r in rows]
    if any(not isinstance(v, str) or not v for v in ids) or len(ids) != len(set(ids)):
        raise ContentError(f'{label}: 식별번호가 비어 있거나 중복됩니다.')


def validate(payload):
    """Validate all collections together before accepting a new revision."""
    from deployment_catalog import validate_catalog
    from public_guidance import load_public_guidance
    if set(payload) != {'data', 'photos'} or set(payload['data']) != set(FILES):
        raise ContentError('관리 데이터 형식이 올바르지 않습니다.')
    data = payload['data']
    try:
        validate_catalog(data['catalog'])
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'guidance.json'
            atomic_json(p, data['tasks'])
            load_public_guidance(p)
    except (ValueError, RuntimeError) as exc:
        raise ContentError(f'업무 안내 형식을 확인해 주세요: {exc}') from None
    ids = {t['id'] for t in data['catalog']['tasks']}
    seen_contacts, primaries = set(), set()
    for c in data['catalog']['contacts']:
        phone(c['phone']); phone(c['display_phone'])
        date_value(c['verified_at'], '연락처 확인일')
        key = (c['task_id'], re.sub(r'\D', '', c['phone']), c['label'])
        if key in seen_contacts:
            raise ContentError('같은 업무에 동일한 연락처가 중복되어 있습니다.')
        seen_contacts.add(key)
        if c['is_primary']:
            if c['task_id'] in primaries:
                raise ContentError('업무별 대표전화는 하나만 선택해 주세요.')
            primaries.add(c['task_id'])
    for row in data['catalog']['aliases']:
        text(row['text'], '검색어', required=True, limit=80)
    all_guides = set()
    for kind in GUIDE_KINDS:
        rows = data[kind]['guides']
        rows_unique(rows, 'id', '사업 안내')
        for g in rows:
            if not GUIDE_FIELDS[kind] <= set(g) or set(g) - GUIDE_FIELDS[kind] - {'active'}:
                raise ContentError('사업 안내에 알 수 없거나 누락된 항목이 있습니다.')
            if g['id'] in all_guides:
                raise ContentError('사업 안내 식별번호가 중복됩니다.')
            all_guides.add(g['id'])
            for field in ['title', 'summary']:
                text(g[field], field, required=True)
            if type(g.get('active', True)) is not bool:
                raise ContentError('공개 여부를 확인해 주세요.')
            for field in ['details', 'keywords']:
                if not isinstance(g[field], list): raise ContentError('내용 또는 검색어 형식 오류')
                for value in g[field]: text(value, field, required=True)
            if not set(g['related_task_ids']) <= ids:
                raise ContentError('연결된 업무가 존재하지 않습니다.')
            for ref in g.get('references', g.get('sources', [])):
                url = urlsplit(ref['url'])
                if url.scheme != 'https' or url.hostname not in OFFICIAL_HOSTS or url.username:
                    raise ContentError('출처에는 지원하는 공식 기관의 HTTPS 주소를 입력해 주세요.')
                text(ref['title'], '출처 이름', required=True)
            for c in g.get('contacts', []):
                phone(c['phone']); text(c['label'], '문의처 이름', required=True)
            if 'phone' in g: phone(g['phone'])
            date_value(g.get('valid_until'), '안내 종료일', optional=True)
            if kind == 'vaccination': date_value(g['checked_on'], '내용 확인일')
    plans = data['plans']
    if not re.fullmatch(r'20\d{2}-(?:0[1-9]|1[0-2])', plans['month']):
        raise ContentError('공개 월은 YYYY-MM 형식으로 입력해 주세요.')
    rows_unique(plans['items'], 'id', '월간 일정')
    for item in plans['items']:
        fields = {'id','source_items','title','department','team','schedule_text','period','schedule_review','location','audience','content','notes','related_tasks'}
        if not fields <= set(item) or set(item) - fields - {'active'}:
            raise ContentError('월간 일정에 알 수 없거나 누락된 항목이 있습니다.')
        if not re.fullmatch(r'MP\d{6}-\d{2,}', item['id']):
            raise ContentError('일정 식별번호 형식이 올바르지 않습니다.')
        for field in ['title', 'department', 'team', 'schedule_text', 'location', 'audience', 'content']:
            text(item[field], field, required=field in ['title', 'schedule_text'])
        if type(item.get('active', True)) is not bool: raise ContentError('일정 공개 여부 오류')
        if type(item['schedule_review']) is not bool or not isinstance(item['notes'], list):
            raise ContentError('일정 확인 여부 또는 추가 안내 형식을 확인해 주세요.')
        for note in item['notes']: text(note, '추가 안내')
        start, end = item['period']['start'], item['period']['end']
        date_value(start, '시작일', optional=True); date_value(end, '종료일', optional=True)
        if start and end and start > end: raise ContentError('종료일이 시작일보다 빠릅니다.')
        for link in item['related_tasks']:
            if link['task_id'] not in ids or link['href'] != '/?task=' + link['task_id']:
                # Original imported links also carry a search query.
                from urllib.parse import parse_qs
                parsed = urlsplit(link['href'])
                if (link['task_id'] not in ids or parsed.scheme or parsed.netloc or parsed.path != '/'
                        or not set(parse_qs(parsed.query)) <= {'q', 'task'}):
                    raise ContentError('일정의 연결 업무를 확인해 주세요.')
    if len(payload['photos']) != 4:
        raise ContentError('홈페이지 사진은 네 장을 선택해 주세요.')
    for photo in payload['photos']:
        if set(photo) != {'asset','alt','caption'}: raise ContentError('사진 정보 형식 오류')
        if not re.fullmatch(r'[0-9a-f]{64}\.(?:jpg|png)', photo['asset']):
            raise ContentError('사진 파일 형식이 올바르지 않습니다.')
        text(photo['alt'], '사진 설명', required=True, limit=150)
        text(photo['caption'], '사진 문구', required=True, limit=150)
    return payload


class Store:
    def __init__(self, root=ROOT, home=None):
        self.root = Path(root).resolve()
        self.home = Path(home or os.getenv('HEALTH_MANAGER_HOME') or self.root / '.tools/site-manager').resolve()
        self.home.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def lock(self):
        with (self.home / 'store.lock').open('a+b') as handle:
            handle.seek(0, 2)
            if not handle.tell(): handle.write(b'0'); handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                try: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError: raise ContentError('다른 저장 작업이 진행 중입니다. 잠시 후 다시 시도해 주세요.') from None
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX)
            try: yield
            finally:
                handle.seek(0)
                if os.name == 'nt': msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else: fcntl.flock(handle, fcntl.LOCK_UN)

    def initialize(self):
        with self.lock():
            if (self.home / 'current.json').exists(): return
            photos = []
            markup = (self.root / 'public/index.html').read_text('utf-8')
            tags = re.findall(r'<img class="hero-slide\b[^>]*>', markup)
            for index, (name, caption) in enumerate(zip(PHOTO_PATHS, PHOTO_CAPTIONS)):
                source = self.root / name
                asset = digest(source) + source.suffix
                target = self.home / 'assets' / asset
                target.parent.mkdir(exist_ok=True)
                if not target.exists(): shutil.copyfile(source, target)
                attributes = dict(re.findall(r'([\w-]+)="([^"]*)"', tags[index])) if len(tags) == 4 else {}
                photos.append(dict(asset=asset, alt=html.unescape(attributes.get('alt', caption)),
                                   caption=html.unescape(attributes.get('data-caption', caption))))
            payload = dict(data={key: read_json(self.root / name) for key, name in FILES.items()}, photos=photos)
            validate(payload)
            revision = self._write(payload, '현재 홈페이지에서 시작', None)
            atomic_json(self.home / 'published.json', {'revision': revision, 'at': now(), 'baseline': True})

    def _write(self, payload, label, parent):
        revision = uuid4().hex
        atomic_json(self.home / 'revisions' / (revision + '.json'),
                    dict(id=revision, at=now(), label=label, parent=parent, payload=payload))
        atomic_json(self.home / 'current.json', {'revision': revision})
        return revision

    def read(self, revision=None):
        self.initialize()
        revision = revision or read_json(self.home / 'current.json')['revision']
        if not re.fullmatch(r'[0-9a-f]{32}', revision): raise ContentError('수정 이력 번호가 올바르지 않습니다.')
        return read_json(self.home / 'revisions' / (revision + '.json'))

    def save(self, payload, expected, label):
        validate(payload)
        for photo in payload['photos']:
            if not (self.home / 'assets' / photo['asset']).is_file(): raise ContentError('사진 원본이 없습니다.')
        with self.lock():
            if read_json(self.home / 'current.json')['revision'] != expected:
                raise ContentError('다른 창에서 내용이 변경됐습니다. 화면을 새로고침한 뒤 다시 수정해 주세요.')
            return self._write(payload, label, expected)

    def history(self):
        return sorted((dict(id=r['id'], at=r['at'], label=r['label'])
                       for p in (self.home / 'revisions').glob('*.json') for r in [read_json(p)]),
                      key=lambda r: (r['at'], r['id']), reverse=True)

    def restore(self, revision, expected):
        return self.save(self.read(revision)['payload'], expected, '이전 내용 복원')

    def add_photo(self, blob):
        from PIL import Image, ImageOps
        if len(blob) > 20 * 1024 * 1024: raise ContentError('사진은 20MB 이하로 선택해 주세요.')
        try:
            with Image.open(BytesIO(blob)) as image:
                if image.format not in {'JPEG', 'PNG', 'WEBP'} or image.width * image.height > 40_000_000:
                    raise ContentError('JPG·PNG·WebP 사진을 선택해 주세요. 최대 4천만 화소입니다.')
                image = ImageOps.exif_transpose(image).convert('RGB')
                output = BytesIO(); image.save(output, 'JPEG', quality=92)
        except (OSError, ValueError): raise ContentError('사진 파일을 읽을 수 없습니다.') from None
        content = output.getvalue(); asset = sha256(content).hexdigest() + '.jpg'
        (self.home / 'assets' / asset).write_bytes(content)
        return asset

    def backup(self):
        revision = self.read()
        output = BytesIO()
        with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
            archive.writestr('content.json', json.dumps(revision, ensure_ascii=False, indent=2))
            for asset in {p['asset'] for p in revision['payload']['photos']}:
                archive.write(self.home / 'assets' / asset, 'assets/' + asset)
        return output.getvalue()

    def import_backup(self, blob, expected):
        if len(blob) > 100 * 1024 * 1024: raise ContentError('백업 파일이 너무 큽니다.')
        with ZipFile(BytesIO(blob)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 150 * 1024 * 1024:
                raise ContentError('백업 파일이 너무 큽니다.')
            record = json.loads(archive.read('content.json'))
            payload = validate(record['payload'])
            for photo in payload['photos']:
                asset = photo['asset']; content = archive.read('assets/' + asset)
                if sha256(content).hexdigest() != asset.split('.')[0]: raise ContentError('백업 사진 검증 실패')
                (self.home / 'assets' / asset).write_bytes(content)
        return self.save(payload, expected, '백업 파일에서 복원')

    def materialize(self, revision, target):
        """Write only managed public files into an already isolated runtime copy."""
        from PIL import Image
        payload = validate(self.read(revision)['payload'])
        target = Path(target)
        for key, name in FILES.items(): atomic_json(target / name, payload['data'][key])
        page = (target / 'public/index.html').read_text('utf-8')
        tags = list(re.finditer(r'<img class="hero-slide\b[^>]*>', page))
        if len(tags) != 4: raise ContentError('홈페이지 사진 영역이 변경되어 확인이 필요합니다.')
        for i in range(3, -1, -1):
            photo = payload['photos'][i]; dest = target / PHOTO_PATHS[i]
            asset = self.home / 'assets' / photo['asset']
            # Original byte-identical photos need no re-encoding.
            if dest.suffix == asset.suffix: shutil.copyfile(asset, dest)
            else:
                with Image.open(asset) as im: im.convert('RGB').save(dest, 'PNG' if dest.suffix == '.png' else 'JPEG')
            tag = tags[i].group()
            for attribute, value in [('alt', photo['alt']), ('data-caption', photo['caption'])]:
                tag = re.sub(r'\b' + attribute + r'="[^"]*"', lambda _: attribute + '="' + html.escape(value, quote=True) + '"', tag)
            page = page[:tags[i].start()] + tag + page[tags[i].end():]
        page = re.sub(r'(<span id="hero-photo-caption">)[^<]*(</span>)',
                      lambda m: m[1] + html.escape(payload['photos'][0]['caption']) + m[2], page)
        (target / 'public/index.html').write_text(page, encoding='utf-8', newline='\n')


def new_guide(payload, kind):
    prefix = {'services': 'S', 'examinations': 'E', 'vaccination': 'V'}[kind]
    rows = payload['data'][kind]['guides']
    number = max(int(g['id'][1:]) for g in rows) + 1
    common = dict(id=f'{prefix}{number:03}', title='', summary='', keywords=[], details=[],
                  related_task_ids=[], caution='', active=False)
    if kind == 'vaccination':
        common.update(sources=[], phone='031-5189-4375', review_required=False, checked_on=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat(), valid_until=None)
    else:
        common.update(references=[], contacts=[], confirmation='', fee='', result_time='')
        if kind == 'examinations': common.update(general_preparation=False, locator='관리자 등록')
        else: common.update(valid_until='', related_task_labels={}, result_category='business')
    return common


def replace_phone(payload, old, new):
    """Keep repeated public contact numbers in guides and task cards consistent."""
    phone(old); phone(new)
    normalized = re.sub(r'\D', '', old)
    count = 0
    def visit(value):
        nonlocal count
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {'phone', 'display_phone'} and isinstance(item, str) and re.sub(r'\D', '', item) == normalized:
                    value[key] = new; count += 1
                    if 'verified_at' in value: value['verified_at'] = datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
                else: visit(item)
        elif isinstance(value, list):
            for item in value: visit(item)
    visit(payload['data'])
    return count
