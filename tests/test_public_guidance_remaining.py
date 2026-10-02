# Baseline includes the official 2026-09-30 M004 eligibility/caution/SMS correction.
"""Remaining-batch evidence scope, historical preservation and no-phone safety."""
import hashlib
import json
from pathlib import Path

import pytest

from app import app, limiter
from public_guidance import load_public_guidance, PublicGuidanceConfigurationError

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = {'A011','A012','R002','A001','A019','H001','H002','M002','M003','M004','M005','M006','M008','A003','F103','F108','F201','A007','A004','F102','F104','F106','F204','A002','A005','A009','M009','F110'}
PHONE = {'H003':'031-5189-6923','M001':'031-5189-6944','R001':'031-5189-5058','R003':'031-5189-5058','R004':'031-5189-5058','R005':'031-5189-4342','R006':'031-5189-4342','D002':'031-5189-4719','A008':'031-5189-5094','A017':'031-5189-4377','A018':'031-5189-4377','F107':'031-5189-4719','F112':'031-352-0175','F305':'031-5189-6916'}
NO_PHONE = {'F109','F111','F202','F203','F206','F301','F302','F303'}
READY = set(PHONE) | NO_PHONE
NO_MAP = {'M001','R001','R003','R004','R005','R006','D002','A008'}
HELD = {'H004','M007','D001','A006','A010','A013','A014','A015','A016','F101','F105','F205','F304'}


def test_previous_28_records_and_125_search_terms_are_unchanged():
    g=load_public_guidance()
    previous=[x for id,x in g.items() if id in PREVIOUS]
    assert len(previous)==28
    assert sum(len(x['public_search_terms']) for x in previous)==125
    canonical=json.dumps(previous,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    assert hashlib.sha256(canonical).hexdigest()=='63da878015d6d80978ab7129919c4db44ba6f7142e6f98313c8358c35d43ffad'
    assert set(g)==PREVIOUS|READY and not set(g)&HELD
    assert sum(len(x['public_search_terms']) for x in g.values())==192


@pytest.mark.parametrize('id',sorted(READY))
def test_remaining_batch_full_search_detail_and_sms_policy(id,monkeypatch,public_guidance_contact_db):
    monkeypatch.setenv('DATA_BACKEND','sqlite')
    monkeypatch.setenv('SQLITE_PATH',str(public_guidance_contact_db))
    monkeypatch.setenv('SMS_MODE','mock')
    monkeypatch.setattr('app.log_event',lambda *a,**k:None)
    monkeypatch.setattr('app.expand_query',lambda q:[])
    monkeypatch.setattr(limiter,'enabled',False)
    client=app.test_client(); g=load_public_guidance()[id]
    for term in g['public_search_terms']:
        r=client.post('/api/search',json={'query':term})
        assert r.status_code==200
        assert r.json['items'][0]['id']==id, (term,r.json['items'])
    detail=client.get('/api/tasks/'+id).json
    assert detail['public_title']==g['public_title']
    assert detail['show_map']==(id not in NO_MAP)
    if id in NO_MAP:
        assert detail['floor'] is None and detail['place'] is None
    else:
        assert detail['floor']==g['location']['floor']
        assert detail['place']==g['location']['room']
    r=client.post('/api/sms',json={'task_id':id,'recipient':'01000000000','consent':True})
    if id in NO_PHONE:
        assert detail['primary_contact'] is None and detail['contacts']==[]
        assert r.status_code==400 and '공식 담당 연락처' in r.json['error']
    else:
        assert detail['primary_contact']['phone']==PHONE[id]
        assert r.status_code==200 and r.json['status']=='mocked'
        preview=r.json['preview']
        assert preview.count(PHONE[id])==1
        for text in [g['public_title'],g['public_caution'],g['location']['route_text']]:
            assert text in preview
        assert not any(x in preview for x in ['source_url','REVIEW_REQUIRED','C:\\'])


def test_current_closure_and_service_specific_boundaries_not_generic_promises():
    g=load_public_guidance()
    assert '신규 접수 종료' in g['R005']['public_caution']
    assert '접수 재개' in g['R005']['primary_action']
    assert '통보 전에' in g['R005']['public_caution']
    assert '소급 지원되지 않습니다' in g['M001']['public_caution']
    assert '성인과 소아' in g['R001']['public_summary']
    assert '19세 이상' in g['R003']['eligibility']
    assert '대신 작성할 수 없습니다' in g['R003']['public_caution']
    assert '현재 접수 중이라는 뜻은 아닙니다' in g['H003']['public_caution']
    assert '재고' in g['R006']['visit_steps']
    assert '검사실은 다릅니다' in g['A008']['public_caution']
    assert '위탁의료기관' in g['A018']['public_caution']
    assert '응급실' in g['F112']['public_caution']
    for id in READY:
        assert g[id]['organization']['team'] is None
        assert g[id]['operating_hours'] is None
        if id.startswith('F'):
            assert all(g[id][k] is None for k in ['documents','fee','operating_hours'])


def test_withdrawn_room_cannot_enable_a_map_from_legacy_floor_place():
    from public_guidance import serialize_public_task
    raw=next(x for x in json.loads((ROOT/'data/tasks.json').read_text(encoding='utf-8')) if x['id']=='F304')
    result=serialize_public_task(raw,[],load_public_guidance())
    assert result['public_title'] is None
    assert result['show_map'] is False
    assert result['floor'] is None and result['place'] is None and result['room'] is None
    assert result['route']=='방문 장소는 전화로 확인해 주세요.'


@pytest.mark.parametrize('term',['건강증진과 과장 이름','건강증진과 과장실 김철수','과장 김철수','건강증진과 과장실 연락처 031-5189-6916'])
def test_verified_room_allowance_never_allows_employee_queries(term,tmp_path):
    payload=json.loads((ROOT/'data/public_guidance.json').read_text(encoding='utf-8'))
    room=next(x for x in payload['tasks'] if x['task_id']=='F305')
    room['public_search_terms'][-1]=term
    p=tmp_path/'unsafe.json';p.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    with pytest.raises(PublicGuidanceConfigurationError):load_public_guidance(p)
