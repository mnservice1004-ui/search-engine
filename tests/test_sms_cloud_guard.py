import json
import uuid
from datetime import datetime

import pytest
import sms_cloud_guard as guard
import sms_service as sms


@pytest.fixture
def cloud(monkeypatch):
    for key in ('KV_REST_API_URL', 'KV_REST_API_TOKEN', 'KV_REST_API_READ_ONLY_TOKEN'):
        monkeypatch.delenv(key, raising=False)
    values = dict(VERCEL='1', SMS_MODE='live', SOLAPI_API_KEY='test-not-real',
                  SOLAPI_API_SECRET='test-not-real', SOLAPI_SENDER='0212345678',
                  UPSTASH_REDIS_REST_URL='https://synthetic.upstash.io',
                  UPSTASH_REDIS_REST_TOKEN='synthetic-token', SMS_GUARD_HMAC_KEY='z' * 64,
                  SMS_GUARD_NAMESPACE='test-only', SMS_ALLOWED_ORIGINS='https://pilot.example.com',
                  SMS_MAX_DAILY='10', SMS_MAX_MONTHLY='100')
    for key, value in values.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize('missing', ['UPSTASH_REDIS_REST_URL', 'UPSTASH_REDIS_REST_TOKEN',
                                    'SMS_GUARD_HMAC_KEY', 'SMS_GUARD_NAMESPACE',
                                    'SMS_MAX_DAILY', 'SMS_MAX_MONTHLY', 'SMS_ALLOWED_ORIGINS'])
def test_cloud_not_ready_without_each_safety_setting(cloud, monkeypatch, missing):
    monkeypatch.delenv(missing)
    assert not sms.sms_capability()['ready']


@pytest.mark.parametrize('mode', ['mock', 'disabled', 'typo', ''])
def test_cloud_never_pretends_to_send_with_mock(cloud, monkeypatch, mode):
    monkeypatch.setenv('SMS_MODE', mode)
    result = sms.sms_capability()
    assert result['ready'] is False and result['mode'] == 'disabled'


@pytest.mark.parametrize('origin', [None, '', 'https://attacker.example', 'http://pilot.example.com'])
def test_unapproved_origins_are_rejected(cloud, origin):
    assert not guard.allowed_origin(origin)


def test_configuration_and_same_origin(cloud):
    assert sms.sms_capability()['ready']
    assert guard.allowed_origin('https://pilot.example.com')
    assert guard.configuration()['daily'] == guard.APPROVED_MAX_DAILY == 10
    assert guard.configuration()['monthly'] == guard.APPROVED_MAX_MONTHLY == 100


def test_vercel_marketplace_credentials_work_without_copying_secrets(cloud, monkeypatch):
    monkeypatch.delenv('UPSTASH_REDIS_REST_URL')
    monkeypatch.delenv('UPSTASH_REDIS_REST_TOKEN')
    monkeypatch.setenv('KV_REST_API_URL', 'https://marketplace.upstash.io')
    monkeypatch.setenv('KV_REST_API_TOKEN', 'synthetic-marketplace-token')
    monkeypatch.setenv('KV_REST_API_READ_ONLY_TOKEN', 'must-not-use-read-only-token')
    config = guard.configuration()
    assert config['url'] == 'https://marketplace.upstash.io'
    assert config['token'] == 'synthetic-marketplace-token'
    assert (config['daily'], config['monthly']) == (10, 100)
    assert sms.sms_capability()['ready']


def test_explicit_upstash_pair_has_priority_over_marketplace_pair(cloud, monkeypatch):
    monkeypatch.setenv('KV_REST_API_URL', 'https://different.upstash.io')
    monkeypatch.setenv('KV_REST_API_TOKEN', 'different-token')
    config = guard.configuration()
    assert config['url'] == 'https://synthetic.upstash.io'
    assert config['token'] == 'synthetic-token'


@pytest.mark.parametrize('missing', ['UPSTASH_REDIS_REST_URL', 'UPSTASH_REDIS_REST_TOKEN'])
def test_incomplete_explicit_pair_never_mixes_or_falls_back(cloud, monkeypatch, missing):
    monkeypatch.delenv(missing)
    monkeypatch.setenv('KV_REST_API_URL', 'https://different.upstash.io')
    monkeypatch.setenv('KV_REST_API_TOKEN', 'different-token')
    assert not guard.configured()


@pytest.mark.parametrize('missing', ['KV_REST_API_URL', 'KV_REST_API_TOKEN'])
def test_incomplete_marketplace_pair_fails_closed(cloud, monkeypatch, missing):
    monkeypatch.delenv('UPSTASH_REDIS_REST_URL')
    monkeypatch.delenv('UPSTASH_REDIS_REST_TOKEN')
    monkeypatch.setenv('KV_REST_API_URL', 'https://marketplace.upstash.io')
    monkeypatch.setenv('KV_REST_API_TOKEN', 'synthetic-token')
    monkeypatch.setenv('KV_REST_API_READ_ONLY_TOKEN', 'read-only-is-not-a-write-token')
    monkeypatch.delenv(missing)
    assert not guard.configured()


@pytest.mark.parametrize('key', ['UPSTASH_REDIS_REST_URL', 'UPSTASH_REDIS_REST_TOKEN'])
def test_empty_explicit_value_is_not_silently_replaced(cloud, monkeypatch, key):
    monkeypatch.setenv(key, '')
    monkeypatch.setenv('KV_REST_API_URL', 'https://different.upstash.io')
    monkeypatch.setenv('KV_REST_API_TOKEN', 'different-token')
    assert not guard.configured()


@pytest.mark.parametrize('daily,monthly', [('0', '100'), ('-1', '100'), ('11', '100'),
                                          ('10', '101'), ('100', '10000'), ('10', '0'),
                                          ('10', '9'), ('ten', '100')])
def test_unapproved_caps_fail_closed_before_redis_or_provider(cloud, monkeypatch, daily, monthly):
    monkeypatch.setenv('SMS_MAX_DAILY', daily)
    monkeypatch.setenv('SMS_MAX_MONTHLY', monthly)
    def forbidden(*args):
        pytest.fail('Invalid caps must be blocked before Redis/provider access')
    monkeypatch.setattr(guard, '_command', forbidden)
    monkeypatch.setattr(sms, '_send_live', forbidden)
    assert not sms.sms_capability()['ready']
    with pytest.raises(guard.CloudSmsUnavailable):
        guard.reserve(str(uuid.uuid4()), '01000000000', 'synthetic-text', '192.0.2.1')


@pytest.mark.parametrize('daily,monthly', [(1, 1), (5, 50), (10, 100)])
def test_lower_limits_allowed_but_approval_ceiling_unchanged(cloud, monkeypatch, daily, monthly):
    monkeypatch.setenv('SMS_MAX_DAILY', str(daily))
    monkeypatch.setenv('SMS_MAX_MONTHLY', str(monthly))
    config = guard.configuration()
    assert (config['daily'], config['monthly']) == (daily, monthly)
    assert (guard.APPROVED_MAX_DAILY, guard.APPROVED_MAX_MONTHLY) == (10, 100)


@pytest.mark.parametrize('utc,day,month', [
    ('2026-09-06T14:59:59+00:00', '20260906', '202609'),
    ('2026-09-06T15:00:00+00:00', '20260907', '202609'),
    ('2026-09-30T14:59:59+00:00', '20260930', '202609'),
    ('2026-09-30T15:00:00+00:00', '20261001', '202610'),
])
def test_day_and_month_keys_follow_korean_calendar(cloud, monkeypatch, utc, day, month):
    instant = datetime.fromisoformat(utc)
    class Clock:
        @staticmethod
        def now(zone):
            assert zone == guard.KOREA_TIME
            return instant.astimezone(zone)
    calls = []
    monkeypatch.setattr(guard, 'datetime', Clock)
    monkeypatch.setattr(guard, '_command', lambda config, parts: calls.append(parts) or ['reserved'])
    guard.reserve(str(uuid.uuid4()), '01000000000', 'synthetic-text', '192.0.2.1')
    keys = calls[0][3:9]
    assert keys[3].startswith('{test-only}:sms:recipient:' + day + ':')
    assert keys[4] == '{test-only}:sms:daily:' + day
    assert keys[5] == '{test-only}:sms:monthly:' + month
    assert calls[0][-2:] == [10, 100]


@pytest.mark.parametrize('url', ['http://synthetic.upstash.io', 'https://attacker.example',
                                'https://synthetic.upstash.io/path', 'https://u:p@synthetic.upstash.io'])
def test_guard_token_never_sent_to_unapproved_endpoint(cloud, monkeypatch, url):
    monkeypatch.setenv('UPSTASH_REDIS_REST_URL', url)
    assert not guard.configured()


@pytest.mark.parametrize('status', ['pending', 'duplicate', 'limited', 'conflict'])
def test_reservation_rejections_do_not_send(cloud, monkeypatch, status):
    monkeypatch.setattr(guard, '_command', lambda *args: [status])
    with pytest.raises(guard.CloudSmsRejected):
        guard.reserve(str(uuid.uuid4()), '01000000000', 'synthetic-text', '192.0.2.1')


def test_reservation_transmits_only_hmac_and_counters(cloud, monkeypatch):
    calls = []
    monkeypatch.setattr(guard, '_command', lambda config, parts: calls.append(parts) or ['reserved'])
    ticket, cached = guard.reserve(str(uuid.uuid4()), '01000000000', 'sensitive-body', '192.0.2.1')
    sent = json.dumps(calls)
    assert all(value not in sent for value in ['01000000000', 'sensitive-body', '192.0.2.1'])
    assert calls[0][0] == 'EVAL' and calls[0][2] == 6
    assert calls[0][-4:] == [3, 3, 10, 100]
    assert cached is None and len(ticket['digest']) == 64


def test_cached_acceptance_and_ambiguous_result(cloud, monkeypatch):
    expected = dict(status='accepted', provider='solapi', message_group_id='synthetic')
    monkeypatch.setattr(guard, '_command', lambda *a: ['cached', json.dumps(expected)])
    assert guard.reserve(str(uuid.uuid4()), '01000000000', 'text', '192.0.2.1')[1] == expected
    monkeypatch.setattr(guard, '_command', lambda *a: ['unknown'])
    with pytest.raises(guard.CloudSmsUnavailable):
        guard.reserve(str(uuid.uuid4()), '01000000000', 'text', '192.0.2.1')


def test_provider_branch_uses_shared_guard_and_pending_survives_error(cloud, monkeypatch):
    calls = []
    task = dict(public_title='합성 안내', route='1층 합성실', primary_contact={'phone': '0212345678'})
    monkeypatch.setattr(guard, 'reserve', lambda *a: ({'key': 'synthetic', 'digest': 'hash'}, None))
    def provider(*args):
        calls.append('send')
        return dict(status='accepted', provider='solapi', message_group_id='synthetic')
    def unavailable(*args):
        raise guard.CloudSmsUnavailable('synthetic offline')
    monkeypatch.setattr(sms, '_send_live', provider)
    monkeypatch.setattr(guard, 'finish', unavailable)
    result = sms.send_contact_sms(task, '01000000000', 'contact', str(uuid.uuid4()), '192.0.2.1')
    assert result['status'] == 'accepted' and calls == ['send'] and 'notice' in result
    monkeypatch.setattr(guard, 'reserve', unavailable)
    with pytest.raises(sms.SmsConfigurationError):
        sms.send_contact_sms(task, '01000000000', 'contact', str(uuid.uuid4()), '192.0.2.1')
    assert calls == ['send']


def test_api_requires_cloud_origin_before_any_lookup(cloud, monkeypatch):
    from app import app, limiter
    monkeypatch.setattr(limiter, 'enabled', False)
    def forbidden(*args):
        pytest.fail('DB or provider must not run for an unapproved origin')
    monkeypatch.setattr('app.get_task', forbidden)
    client = app.test_client()
    for headers in ({}, {'Origin': 'https://attacker.example'}):
        assert client.post('/api/sms', json={}, headers=headers).status_code == 403


def test_network_error_does_not_expose_token(cloud, monkeypatch):
    class Broken:
        def open(self, *args, **kwargs):
            raise RuntimeError('synthetic-token synthetic-private-response')
    monkeypatch.setattr(guard, 'build_opener', lambda *args: Broken())
    with pytest.raises(guard.CloudSmsUnavailable) as error:
        guard._command(guard.configuration(), ['GET', 'synthetic'])
    assert 'synthetic-token' not in str(error.value) and 'private-response' not in str(error.value)
