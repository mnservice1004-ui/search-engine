import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import sms_service as sms
from app import app, limiter


def task(phone=True):
    return dict(id='F108', public_title='민원실 위치 안내', public_summary='공개 위치 안내',
                eligibility='민원실을 찾는 분', route='1층 민원실', documents='신분증', fee=None,
                operating_hours=None, visit_steps='접수 장소를 확인하세요.', public_caution='방문 전에 확인하세요.',
                primary_action='전화로 확인하세요.', primary_contact={'phone':'0311234567'} if phone else None,
                _sms_fields=['location','primary_action','public_caution'])


def test_guidance_includes_details_without_a_contact_and_contact_mode_is_short():
    text=sms.build_message(task(False),'guidance')
    assert all(x in text for x in ['공개 위치 안내','민원실을 찾는 분','신분증','접수 장소를 확인하세요.','방문 전에 확인하세요.'])
    assert '문의:' not in text
    contact=sms.build_message(task(),'contact')
    assert '문의: 0311234567' in contact and '대상:' not in contact and '준비물:' not in contact
    with pytest.raises(ValueError):sms.build_message(task(False),'contact')
    with pytest.raises(ValueError):sms.build_message(task(),'arbitrary')
    with pytest.raises(ValueError):sms.build_message(task(),['guidance'])


@pytest.mark.parametrize('mode',['LIVE_TYPO','live'])
def test_bad_or_missing_live_config_does_not_silently_mock(monkeypatch,mode):
    monkeypatch.setenv('SMS_MODE',mode)
    for key in ['SOLAPI_API_KEY','SOLAPI_API_SECRET','SOLAPI_SENDER']:monkeypatch.delenv(key,raising=False)
    with pytest.raises(sms.SmsConfigurationError):sms.send_contact_sms(task(),'01000000000','guidance',str(uuid.uuid4()))


def configure_live(monkeypatch):
    monkeypatch.setenv('SMS_MODE','live')
    monkeypatch.setenv('SOLAPI_API_KEY','test-key-not-real')
    monkeypatch.setenv('SOLAPI_API_SECRET','test-secret-not-real')
    monkeypatch.setenv('SOLAPI_SENDER','0212345678')


def test_real_sdk_branch_validates_acceptance_and_deduplicates(monkeypatch):
    import solapi
    configure_live(monkeypatch);calls=[]
    class Provider:
        def __init__(self,**kwargs):pass
        def send(self,message):
            calls.append(message)
            return SimpleNamespace(failed_message_list=[],group_info=SimpleNamespace(group_id='test-group',count=SimpleNamespace(registered_success=1)))
    monkeypatch.setattr(solapi,'SolapiMessageService',Provider)
    key=str(uuid.uuid4())
    first=sms.send_contact_sms(task(False),'01000000000','guidance',key)
    second=sms.send_contact_sms(task(False),'01000000000','guidance',key)
    assert first==second and first['status']=='accepted' and len(calls)==1
    assert calls[0].from_=='0212345678' and calls[0].to=='01000000000' and '준비물: 신분증' in calls[0].text
    with pytest.raises(ValueError):sms.send_contact_sms(task(False),'01000000001','guidance',key)


@pytest.mark.parametrize('failure',['rejected','exception'])
def test_provider_failure_is_not_success_and_secrets_do_not_escape(monkeypatch,failure):
    import solapi
    configure_live(monkeypatch);calls=[]
    class Provider:
        def __init__(self,**kwargs):pass
        def send(self,message):
            calls.append(1)
            if failure=='exception':raise RuntimeError('secret-and-recipient-must-not-escape')
            return SimpleNamespace(failed_message_list=[object()],group_info=SimpleNamespace(count=SimpleNamespace(registered_success=0)))
    monkeypatch.setattr(solapi,'SolapiMessageService',Provider)
    key=str(uuid.uuid4())
    with pytest.raises(sms.SmsDeliveryError) as err:sms.send_contact_sms(task(),'01000000000','guidance',key)
    assert 'secret-and-recipient' not in str(err.value)
    with pytest.raises(sms.SmsDeliveryError):sms.send_contact_sms(task(),'01000000000','guidance',key)
    assert len(calls)==1


def test_preview_and_content_only_send_for_missing_contact(monkeypatch, public_guidance_contact_db):
    monkeypatch.setenv('SMS_MODE','mock');monkeypatch.setattr(limiter,'enabled',False)
    monkeypatch.setenv('DATA_BACKEND','sqlite')
    monkeypatch.setenv('SQLITE_PATH',str(public_guidance_contact_db))
    c=app.test_client()
    data={'task_id':'F109','message_kind':'guidance'}
    preview=c.post('/api/sms/preview',json=data)
    assert preview.status_code==200 and preview.json['ready'] and preview.json['mode']=='mock'
    assert '모자보건실' in preview.json['text']
    sent=c.post('/api/sms',json={**data,'consent':True,'recipient':'01000000000','request_id':str(uuid.uuid4())})
    assert sent.status_code==200 and sent.json['preview']==preview.json['text']
    assert c.post('/api/sms/preview',json={**data,'message_kind':'contact'}).status_code==400
    assert c.post('/api/sms',json={**data,'consent':False,'recipient':'01000000000'}).status_code==400
    assert c.post('/api/sms/preview',json=data,headers={'Origin':'https://attacker.invalid'}).status_code==403


def test_all_guides_fit_one_lms_without_truncation():
    rows=json.loads((Path(__file__).resolve().parents[1]/'data/public_guidance.json').read_text(encoding='utf-8'))['tasks']
    for row in rows:
        item={**row,'route':row['location']['route_text']}
        text=sms.build_message(item,'guidance')
        assert row['public_caution'].replace('대표전화','문의전화') in text
        assert len(text.encode('euc-kr','replace'))<=2000
