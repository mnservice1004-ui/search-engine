"""Shared, fail-closed SMS reservations for Vercel workers (Upstash REST).

Only HMAC digests and counters are persisted: no phone, IP or message text.
An uncertain provider response keeps its reservation; we never auto-retry SMS.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


# User-approved shared pilot limits, 2026-09-06. Lower environment limits are
# allowed; increasing these ceilings requires a separately approved code change.
APPROVED_MAX_DAILY = 10
APPROVED_MAX_MONTHLY = 100
KOREA_TIME = timezone(timedelta(hours=9))


class CloudSmsUnavailable(RuntimeError):
    pass


class CloudSmsRejected(RuntimeError):
    pass


RESERVE_LUA = """
local old = redis.call('GET', KEYS[1])
if old then
  local previous = cjson.decode(old)
  if previous.digest ~= ARGV[1] then return {'conflict'} end
  if previous.result then return {'cached', cjson.encode(previous.result)} end
  return {'pending'}
end
if redis.call('EXISTS', KEYS[2]) == 1 then return {'duplicate'} end
for i=3,6 do
  if tonumber(redis.call('GET', KEYS[i]) or '0') >= tonumber(ARGV[i-1]) then
    return {'limited'}
  end
end
redis.call('SET', KEYS[1], cjson.encode({digest=ARGV[1]}), 'EX', 86400)
redis.call('SET', KEYS[2], '1', 'EX', 600)
local lifetimes = {60, 172800, 172800, 2764800}
for i=3,6 do
  local n = redis.call('INCR', KEYS[i])
  if n == 1 then redis.call('EXPIRE', KEYS[i], lifetimes[i-2]) end
end
return {'reserved'}
"""
FINISH_LUA = """
local old = redis.call('GET', KEYS[1])
if not old then return 0 end
local previous = cjson.decode(old)
if previous.digest ~= ARGV[1] then return 0 end
previous.result = cjson.decode(ARGV[2])
redis.call('SET', KEYS[1], cjson.encode(previous), 'KEEPTTL')
return 1
"""


def configuration():
    # Vercel Marketplace injects KV_* automatically. Select a complete naming
    # scheme, never mix a URL from one database with another database's token.
    url_key, token_key = 'UPSTASH_REDIS_REST_URL', 'UPSTASH_REDIS_REST_TOKEN'
    if url_key not in os.environ and token_key not in os.environ:
        url_key, token_key = 'KV_REST_API_URL', 'KV_REST_API_TOKEN'
    url = os.getenv(url_key, '').strip().rstrip('/')
    token = os.getenv(token_key, '').strip()
    secret = os.getenv('SMS_GUARD_HMAC_KEY', '').strip()
    namespace = os.getenv('SMS_GUARD_NAMESPACE', '').strip()
    origins = [v.strip().rstrip('/') for v in os.getenv('SMS_ALLOWED_ORIGINS', '').split(',') if v.strip()]
    parsed = urlsplit(url)
    try:
        daily = int(os.getenv('SMS_MAX_DAILY', '0'))
        monthly = int(os.getenv('SMS_MAX_MONTHLY', '0'))
    except ValueError:
        daily = monthly = 0
    valid_origins = bool(origins) and all(
        urlsplit(o).scheme == 'https' and urlsplit(o).netloc and
        not urlsplit(o).username and not urlsplit(o).path and
        not urlsplit(o).query and not urlsplit(o).fragment for o in origins)
    valid = (parsed.scheme == 'https' and (parsed.hostname or '').endswith('.upstash.io')
             and not parsed.username and parsed.port in (None, 443)
             and not parsed.path and not parsed.query and not parsed.fragment
             and token and not token.startswith('YOUR_') and len(secret) >= 32
             and not secret.startswith('YOUR_')
             and re.fullmatch(r'[A-Za-z0-9_-]{1,40}', namespace or '')
             and 1 <= daily <= APPROVED_MAX_DAILY
             and daily <= monthly <= APPROVED_MAX_MONTHLY and valid_origins)
    if not valid:
        raise CloudSmsUnavailable('공개 문자 발송의 보안·한도 설정이 완료되지 않았습니다.')
    return dict(url=url, token=token, secret=secret, namespace=namespace,
                daily=daily, monthly=monthly, origins=origins)


def configured():
    try:
        configuration()
        return True
    except (CloudSmsUnavailable, ValueError):
        return False


def allowed_origin(origin):
    try:
        return bool(origin) and origin.rstrip('/') in configuration()['origins']
    except (CloudSmsUnavailable, ValueError):
        return False


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _command(config, parts):
    request = Request(config['url'], data=json.dumps(parts).encode(),
                      headers={'Authorization': 'Bearer ' + config['token'],
                               'Content-Type': 'application/json'}, method='POST')
    try:
        with build_opener(_NoRedirect()).open(request, timeout=6) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError('oversized')
        payload = json.loads(raw)
        if 'error' in payload or 'result' not in payload:
            raise ValueError('missing result')
        return payload['result']
    except Exception:
        raise CloudSmsUnavailable('문자 발송 안전장치에 연결할 수 없습니다. 발송하지 않았거나 결과 확인이 필요합니다.') from None


def reserve(request_id, recipient, text, client_ip):
    config = configuration()
    try:
        address = str(ipaddress.ip_address(client_ip))
    except (ValueError, TypeError):
        raise CloudSmsUnavailable('요청 출처를 확인할 수 없어 문자를 발송하지 않았습니다.') from None
    def digest(value):
        return hmac.new(config['secret'].encode(), value.encode(), hashlib.sha256).hexdigest()
    prefix = '{' + config['namespace'] + '}:sms:'
    fingerprint = digest(recipient + '\0' + text)
    now = datetime.now(KOREA_TIME)
    keys = [prefix + 'request:' + digest(request_id), prefix + 'body:' + fingerprint,
            prefix + 'ip:' + digest(address),
            prefix + 'recipient:' + now.strftime('%Y%m%d') + ':' + digest(recipient),
            prefix + 'daily:' + now.strftime('%Y%m%d'), prefix + 'monthly:' + now.strftime('%Y%m')]
    reply = _command(config, ['EVAL', RESERVE_LUA, len(keys), *keys,
                              fingerprint, 3, 3, config['daily'], config['monthly']])
    if not isinstance(reply, list) or not reply:
        raise CloudSmsUnavailable('문자 발송 예약을 확인할 수 없습니다.')
    ticket = dict(key=keys[0], digest=fingerprint)
    if reply[0] == 'reserved':
        return ticket, None
    if reply[0] == 'cached':
        try:
            result = json.loads(reply[1])
            if result.get('status') != 'accepted' or result.get('provider') != 'solapi':
                raise ValueError()
            return ticket, result
        except (ValueError, IndexError, AttributeError):
            raise CloudSmsUnavailable('기존 발송 결과를 확인할 수 없습니다.') from None
    if reply[0] == 'conflict':
        raise CloudSmsRejected('발송 확인 정보와 내용이 다릅니다. 문자 창을 다시 열어 주세요.')
    if reply[0] == 'limited':
        raise CloudSmsRejected('시범 운영 문자 발송 한도에 도달했습니다. 화면의 안내 내용을 이용해 주세요.')
    if reply[0] in ('pending', 'duplicate'):
        raise CloudSmsRejected('동일한 문자가 처리 중이거나 이미 접수되었습니다. 중복 발송하지 마세요.')
    raise CloudSmsUnavailable('문자 발송 예약 상태가 올바르지 않습니다.')


def finish(ticket, result):
    safe_result = {key: result[key] for key in ('status', 'provider', 'message_group_id')}
    if _command(configuration(), ['EVAL', FINISH_LUA, 1, ticket['key'], ticket['digest'],
                                   json.dumps(safe_result)]) != 1:
        raise CloudSmsUnavailable('발송은 접수되었으나 중복 방지 기록 확인이 필요합니다.')
