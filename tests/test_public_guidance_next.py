# Baseline includes the official 2026-09-30 M004 eligibility/caution/SMS correction.
"""Second evidence-backed batch, with fixed historical records and service boundaries."""
import hashlib
import json
from pathlib import Path

import pytest

from app import app, build_verified_map_target_registry, limiter, search_public_tasks
from public_guidance import build_public_search_tasks, load_public_guidance

ROOT = Path(__file__).resolve().parents[1]
READY = {
    'A002': ('민원실', '031-5189-4369'),
    'A005': ('모자보건실·예방접종실', '031-5189-5076'),
    'A009': ('민원실', '031-5189-5094'),
    'M009': ('모자보건실·예방접종실', '031-5189-4375'),
    'F110': ('모자보건교육실(수유실)', '031-5189-5076'),
}


def test_previous_twenty_three_records_and_102_terms_are_byte_equivalent_canonically():
    guidance = load_public_guidance()
    previous = [item for key, item in guidance.items() if key in {'H002', 'F106', 'M004', 'F201', 'A012', 'M002', 'A004', 'A011', 'M008', 'F103', 'H001', 'A019', 'M005', 'M003', 'R002', 'F104', 'F102', 'F108', 'A001', 'A007', 'A003', 'M006', 'F204'}]
    canonical = json.dumps(previous, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    assert len(previous) == 23
    assert sum(len(x['public_search_terms']) for x in previous) == 102
    assert hashlib.sha256(canonical).hexdigest() == 'eacd5f331e159d963a0c040aa2e736c0429c768d1f4ac28db0ec31fb0d8ca9c8'


@pytest.mark.parametrize('task_id', READY)
def test_next_batch_search_detail_and_mock_sms(task_id, monkeypatch, public_guidance_contact_db):
    monkeypatch.setenv('DATA_BACKEND', 'sqlite')
    monkeypatch.setenv('SQLITE_PATH', str(public_guidance_contact_db))
    monkeypatch.setenv('SMS_MODE', 'mock')
    monkeypatch.setattr('app.log_event', lambda *args, **kwargs: None)
    monkeypatch.setattr('app.expand_query', lambda query: [])
    monkeypatch.setattr(limiter, 'enabled', False)
    app.config.update(TESTING=True)
    client = app.test_client()
    item = load_public_guidance()[task_id]
    for term in item['public_search_terms']:
        response = client.post('/api/search', json={'query': term})
        assert response.status_code == 200
        assert response.json['items'][0]['id'] == task_id
    response = client.get(f'/api/tasks/{task_id}')
    assert response.status_code == 200
    detail = response.json
    room, phone = READY[task_id]
    assert (detail['floor'], detail['place'], detail['show_map']) == ('1층', room, True)
    assert detail['public_title'] == item['public_title']
    assert detail['primary_contact']['phone'] == phone
    assert sum(c['is_primary'] for c in detail['contacts']) == 1
    assert detail['verified_date'] == '2026-09-06'
    response = client.post('/api/sms', json={'task_id': task_id, 'recipient': '01000000000', 'consent': True})
    assert response.status_code == 200 and response.json['status'] == 'mocked'
    preview = response.json['preview']
    for text in [item['public_title'], item['location']['route_text'], item['public_caution']]:
        assert text in preview
    assert preview.count(phone) == 1
    assert all(c['phone'] not in preview for c in detail['contacts'] if not c['is_primary'])
    assert not any(x in preview for x in ['source_url', '검수', 'confirmed', 'C:\\'])


def test_new_content_preserves_specific_service_branches_and_unknown_values():
    g = load_public_guidance()
    assert g['A002']['organization']['team'] is None
    assert g['A009']['organization']['team'] is None
    assert g['A005']['organization'] == {'department': '건강증진과', 'team': '모자보건팀'}
    assert '모든 검사에 금식이 필요한 것은 아닙니다' in g['A002']['public_caution']
    assert '민원실 접수가 필요한' in g['A002']['location']['route_text']
    assert '성병그린검진' in g['A009']['visit_steps']
    assert '진료실 → 검사실 → 진료실' in g['A009']['visit_steps']
    assert '익명 HIV' in g['A009']['public_caution']
    assert g['A009']['fee'] is None and g['A009']['operating_hours'] is None
    assert '월·화·목' in g['M009']['operating_hours']
    assert '성인 접종' in g['M009']['operating_hours']
    assert '위탁의료기관' in g['M009']['public_caution']
    assert '안내받은 경우에만' in g['M009']['location']['route_text']
    assert '영양제 안내' in g['A005']['operating_hours'] and '초기·막달 검사 안내' in g['A005']['operating_hours']
    assert g['A005']['fee'] is None
    assert '2층 대강당' in g['F110']['public_caution']
    assert all(g['F110'][key] is None for key in ['documents', 'fee', 'operating_hours'])
    assert {'F101', 'F304', 'M007'}.isdisjoint(g)


def test_next_batch_keeps_existing_registered_places_and_other_tasks_held():
    g = load_public_guidance()
    raw = json.loads((ROOT / 'data/tasks.json').read_text(encoding='utf-8'))
    for task in raw:
        if task['id'] in READY:
            location = g[task['id']]['location']
            assert (location['floor'], location['room']) == (task['floor'], task['place'])
    assert len(g) == 50
    assert len([x for x in raw if x['id'] not in g]) == 13


@pytest.mark.parametrize(('query', 'expected'), [('민원실', 'F108'), ('모자보건실', 'F109'), ('예방접종실', 'F109'), ('수유실', 'F110')])
def test_service_guidance_does_not_steal_exact_facility_queries(query, expected):
    raw = json.loads((ROOT / 'data/tasks.json').read_text(encoding='utf-8'))
    searchable = build_public_search_tasks(raw, load_public_guidance())
    points = json.loads((ROOT / 'data/map_points.json').read_text(encoding='utf-8'))
    registry = build_verified_map_target_registry(raw, points)
    assert search_public_tasks(searchable, query, 10, registry)[0]['id'] == expected
