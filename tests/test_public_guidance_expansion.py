# Baseline includes the official 2026-09-30 M004 eligibility/caution/SMS correction.
"""Five evidence-backed additions; no operational DB or workbook dependency."""
import hashlib
import json
from pathlib import Path

import pytest

from app import app, limiter, search_public_tasks
from public_guidance import build_public_search_tasks, load_public_guidance

ROOT = Path(__file__).resolve().parents[1]
READY = {
    'A004': ('1층', '검사실', '031-5189-5094'),
    'F102': ('1층', '영상의학실(방사선실)', '031-5189-4344'),
    'F104': ('1층', '검사실', '031-5189-4369'),
    'F106': ('1층', '재활보건실', '031-5189-4342'),
    'F204': ('2층', '금연상담실', '031-5189-4371'),
}


def test_all_previous_eighteen_complete_records_and_eighty_three_terms_are_preserved():
    guidance = load_public_guidance()
    historical_ids = {'A001', 'A003', 'A007', 'A011', 'A012', 'A019', 'F103', 'F108', 'F201', 'H001', 'H002', 'M002', 'M003', 'M004', 'M005', 'M006', 'M008', 'R002'}
    original = [item for key, item in guidance.items() if key in historical_ids]
    canonical = json.dumps(original, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    assert len(original) == 18
    assert sum(len(x['public_search_terms']) for x in original) == 83
    assert hashlib.sha256(canonical).hexdigest() == 'fc8fc8c0359f7b75cb2c87bc0bfd74135942cdd0c25ebb87a6a3dd6a706dc203'


@pytest.mark.parametrize('task_id', READY)
def test_additional_guidance_search_detail_and_mock_sms(task_id, monkeypatch, public_guidance_contact_db):
    monkeypatch.setenv('DATA_BACKEND', 'sqlite')
    monkeypatch.setenv('SQLITE_PATH', str(public_guidance_contact_db))
    monkeypatch.setenv('ENABLE_LLM', 'false')
    monkeypatch.setenv('SMS_MODE', 'mock')
    monkeypatch.setattr('app.log_event', lambda *args, **kwargs: None)
    monkeypatch.setattr('app.expand_query', lambda query: [])
    monkeypatch.setattr(limiter, 'enabled', False)
    app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    client = app.test_client()
    guidance = load_public_guidance()[task_id]
    for term in guidance['public_search_terms']:
        response = client.post('/api/search', json={'query': term})
        assert response.status_code == 200
        assert response.json['items'][0]['id'] == task_id
    detail = client.get(f'/api/tasks/{task_id}').json
    floor, room, phone = READY[task_id]
    assert (detail['floor'], detail['place'], detail['show_map']) == (floor, room, True)
    assert detail['public_title'] == guidance['public_title']
    assert detail['primary_contact']['phone'] == phone
    assert sum(c['is_primary'] for c in detail['contacts']) == 1
    assert detail['documents'] is None
    if task_id != 'A004':
        assert detail['fee'] is None
    assert detail['verified_date'] == '2026-09-06'
    response = client.post('/api/sms', json={'task_id': task_id, 'recipient': '01000000000', 'consent': True})
    assert response.status_code == 200
    assert response.json['status'] == 'mocked'
    preview = response.json['preview']
    assert guidance['public_title'] in preview
    assert guidance['location']['route_text'] in preview
    assert preview.count(phone) == 1
    assert guidance['public_caution'] in preview
    assert all(c['phone'] not in preview for c in detail['contacts'] if not c['is_primary'])
    assert not any(x in preview for x in ['source_url', '검수', 'confirmed', 'C:\\'])


def test_added_guidance_does_not_repurpose_maps_or_unconfirmed_services():
    guidance = load_public_guidance()
    raw = json.loads((ROOT / 'data/tasks.json').read_text(encoding='utf-8'))
    for task in raw:
        if task['id'] in READY:
            location = guidance[task['id']]['location']
            assert (location['floor'], location['room']) == (task['floor'], task['place'])
    assert len([x for x in raw if x['id'] not in guidance]) == 13
    assert {'F101', 'M007', 'F304'}.isdisjoint(guidance)
    assert guidance['A004']['documents'] is None
    assert '민원실이 아닌' in guidance['A004']['location']['route_text']
    assert '대여·반납' in guidance['F106']['public_caution']
    assert '업무별로 확인' in guidance['F106']['public_caution']
    assert '예약' in guidance['F204']['operating_hours']


def test_exact_facility_first_place_is_preserved_after_guidance_additions():
    raw = json.loads((ROOT / 'data/tasks.json').read_text(encoding='utf-8'))
    searchable = build_public_search_tasks(raw, load_public_guidance())
    for query, expected in [('방사선실', 'F102'), ('영상의학실', 'F102'), ('검사실', 'F104'), ('재활보건실', 'F106'), ('금연상담실', 'F204')]:
        assert search_public_tasks(searchable, query, 10)[0]['id'] == expected
