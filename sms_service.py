import os
import re
import hashlib
import json
import logging
import threading
import time
import uuid


class SmsConfigurationError(RuntimeError):
    pass


class SmsDeliveryError(RuntimeError):
    def __init__(self, message, *, delivery_status=None, diagnostic_id=None, category=None):
        super().__init__(message)
        self.delivery_status = delivery_status
        self.diagnostic_id = diagnostic_id
        self.category = category


_send_lock = threading.Lock()
_send_requests = {}  # Process-local, short-lived hashes only; no recipient/text log.


def _solapi_settings():
    # Use the same outer-whitespace normalization for readiness and SDK calls.
    return tuple(os.getenv(key, "").strip() for key in
                 ("SOLAPI_API_KEY", "SOLAPI_API_SECRET", "SOLAPI_SENDER"))


def sms_capability():
    cloud = os.getenv("VERCEL") == "1"
    mode = os.getenv("SMS_MODE", "disabled" if cloud else "mock").strip().lower()
    values = _solapi_settings()
    configured = all(values) and all(not v.upper().startswith("YOUR_") for v in values)
    configured = configured and bool(re.fullmatch(r"\d{8,11}", values[2]))
    ready = mode == "mock" or (mode == "live" and configured)
    if cloud:
        from sms_cloud_guard import configured as guard_configured
        ready = mode == 'live' and configured and guard_configured()
        if not ready:
            return {'mode': mode if mode == 'live' else 'disabled', 'ready': False,
                    'notice': '공개 문자 발송의 연결·보안·한도 설정이 완료되지 않았습니다. 실제 발송은 아직 사용할 수 없습니다.'}
    return {"mode": mode if mode in {"mock", "live"} else "invalid", "ready": bool(ready),
            "notice": ("모의 발송 모드입니다. 실제 문자는 발송되지 않습니다." if mode == "mock"
                       else "실제 문자 발송 모드입니다. 발송 비용이 발생할 수 있습니다." if ready
                       else "실제 문자 발송 설정이 완료되지 않았습니다. 관리자에게 문의해 주세요.")}

KOREAN_MOBILE = re.compile(r"^01[016789]\d{7,8}$")


def normalize_mobile(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if not KOREAN_MOBILE.fullmatch(digits):
        raise ValueError("휴대전화번호 형식이 올바르지 않습니다.")
    return digits


def _public_text(task, field):
    value = task.get(field)
    return str(value).strip() if isinstance(value, str) and value.strip() else ""


def _primary_contact(task):
    contact = task.get("primary_contact")
    if isinstance(contact, dict) and (
        contact.get("phone") or contact.get("display_phone")
    ):
        return contact

    contacts = task.get("contacts")
    if isinstance(contacts, list):
        return next(
            (
                item
                for item in contacts
                if isinstance(item, dict)
                and item.get("is_primary")
                and (item.get("phone") or item.get("display_phone"))
            ),
            None,
        )
    return None


SMS_FIELD_LABELS = {
    "public_summary": "안내",
    "eligibility": "대상",
    "location": "장소",
    "documents": "준비물",
    "fee": "비용",
    "operating_hours": "이용시간",
    "visit_steps": "이용방법",
    "primary_action": "이용방법",
    "public_caution": "꼭 확인",
}


def _selected_sms_fields(task):
    fields = task.get("_sms_fields")
    if not isinstance(fields, (list, tuple)) or not 2 <= len(fields) <= 5:
        raise ValueError("공개 안내 문자 구성이 올바르지 않습니다.")
    if len(set(fields)) != len(fields) or "location" not in fields:
        raise ValueError("공개 안내 문자 구성이 올바르지 않습니다.")
    if any(field not in SMS_FIELD_LABELS for field in fields):
        raise ValueError("공개 안내 문자 구성이 올바르지 않습니다.")
    if {"visit_steps", "primary_action"} <= set(fields):
        raise ValueError("공개 안내 문자 구성이 올바르지 않습니다.")
    return fields


def _sms_field_value(task, field):
    if field == "location":
        value = _public_text(task, "route")
    else:
        value = _public_text(task, field)
    # 화면과 문자 모두 한 개의 문의번호를 안내하므로, 필드 안의 기존
    # "대표전화" 표기도 외부 안내용 표현인 "문의전화"로만 바꾼다.
    return value.replace("대표전화", "문의전화")


def build_message(task, message_kind="combined"):
    if not isinstance(message_kind, str) or message_kind not in {"contact", "guidance", "combined"}:
        raise ValueError("문자 내용 종류가 올바르지 않습니다.")
    title = _public_text(task, "public_title")
    if not title:
        raise ValueError("공개 안내가 등록되지 않은 업무는 문자 발송할 수 없습니다.")

    primary_contact = _primary_contact(task) or {}
    phone = str(
        primary_contact.get("display_phone") or primary_contact.get("phone") or ""
    ).strip()
    if not phone and message_kind != "guidance":
        raise ValueError("공식 담당 연락처가 아직 등록되지 않았습니다.")
    fields = ([] if message_kind == "contact" else
              ["public_summary", "eligibility", "location", "documents", "fee", "operating_hours", "visit_steps", "public_caution"]
              if message_kind == "guidance" else _selected_sms_fields(task))
    lines = ["[동탄구보건소]", f"업무: {title}"]
    for field in fields:
        value = _sms_field_value(task, field)
        if value:
            lines.append(f"{SMS_FIELD_LABELS[field]}: {value}")
    if phone:
        lines.append(f"문의: {phone}")
    text = "\n".join(lines)
    if len(text.encode('euc-kr', 'replace')) > 2000:
        raise ValueError("안내 내용이 장문 문자 한도보다 깁니다. 내용을 임의로 잘라 발송하지 않습니다.")
    return text


def send_contact_sms(task, recipient, message_kind="combined", request_id=None, client_ip=None):
    recipient = normalize_mobile(recipient)
    text = build_message(task, message_kind)
    capability = sms_capability()
    if not capability['ready']:
        raise SmsConfigurationError(capability['notice'])
    if capability['mode'] == 'live' and not request_id:
        raise ValueError("발송 확인 정보가 없습니다. 문자 창을 다시 열어 주세요.")
    if request_id is not None:
        try:
            request_id = str(uuid.UUID(str(request_id)))
        except ValueError:
            raise ValueError("발송 확인 정보가 올바르지 않습니다.") from None
    if os.getenv('VERCEL') == '1':
        from sms_cloud_guard import reserve, finish, CloudSmsUnavailable, CloudSmsRejected
        try:
            ticket, cached = reserve(request_id, recipient, text, client_ip)
        except CloudSmsUnavailable as error:
            raise SmsConfigurationError(str(error)) from None
        except CloudSmsRejected as error:
            raise SmsDeliveryError(str(error)) from None
        if cached:
            return cached
        result = _send_live(recipient, text)
        try:
            finish(ticket, result)
        except CloudSmsUnavailable:
            # The provider accepted it: do not turn acceptance into a retry.
            # The shared pending reservation still prevents a duplicate send.
            result['notice'] = '발송이 접수되었습니다. 중복 발송하지 마세요.'
        return result
    digest = hashlib.sha256((recipient + '\0' + text + '\0' + capability['mode']).encode()).hexdigest()
    if request_id:
        with _send_lock:
            for key, entry in list(_send_requests.items()):
                if time.monotonic() - entry['time'] > 600:
                    del _send_requests[key]
            previous = _send_requests.get(request_id)
            if previous:
                if previous['digest'] != digest:
                    raise ValueError("발송 확인 정보와 내용이 다릅니다. 문자 창을 다시 열어 주세요.")
                if previous.get('result'):
                    return dict(previous['result'])
                raise SmsDeliveryError("이 요청은 처리 중이거나 발송 결과 확인이 필요합니다. 중복 발송하지 마세요.")
            if len(_send_requests) >= 1000:
                raise SmsDeliveryError("발송 요청이 많습니다. 잠시 후 다시 이용해 주세요.")
            _send_requests[request_id] = {'digest': digest, 'time': time.monotonic()}
    if capability['mode'] == 'mock':
        result = {"status": "mocked", "provider": "mock", "preview": text}
    else:
        result = _send_live(recipient, text)
    if request_id:
        with _send_lock:
            _send_requests[request_id]['result'] = dict(result)
    return result


# Only fixed, reviewed codes may cross the provider-to-log boundary. Never log
# exception strings, failed_messages, payloads, credentials or response bodies.
# Numeric meanings: https://solapi.com/message-status-codes
_PROVIDER_CODES = {
    '1010': 'request_invalid', '1011': 'request_invalid',
    '1013': 'request_invalid', '1014': 'request_invalid',
    '1020': 'provider_authentication', '1025': 'request_invalid',
    '1026': 'provider_duplicate', '1027': 'request_invalid',
    '1028': 'request_invalid', '1029': 'request_invalid',
    '1030': 'provider_balance', '1031': 'request_invalid',
    '1060': 'provider_sender', '1062': 'provider_sender',
    '2062': 'provider_sender', '2230': 'provider_balance',
    'InvalidApiKey': 'provider_authentication',
    'InvalidAPIKey': 'provider_authentication',
    'SignatureDoesNotMatch': 'provider_authentication',
    'Unauthorized': 'provider_authentication',
    'Forbidden': 'provider_authentication',
    'IpNotAllowed': 'provider_authentication',
    'InvalidIp': 'provider_authentication',
    'NotEnoughBalance': 'provider_balance',
    'NotEnoughCash': 'provider_balance',
    'TooManyRequests': 'provider_rate_limit',
}
_FAILURE_MESSAGES = {
    'not_sent': '문자 발송 준비 중 오류가 발생하여 발송 요청을 보내지 않았습니다. 관리자에게 문의해 주세요.',
    'unknown': '문자 발송 결과를 확인할 수 없습니다. 중복 발송하지 말고 관리자에게 발송 내역 확인을 요청해 주세요.',
    'rejected': '발송 서비스가 문자 접수를 거절했습니다. 재발송 전에 관리자에게 확인을 요청해 주세요.',
}
_REJECTION_MESSAGES = {
    'provider_authentication': '발송 서비스 인증 또는 접근 권한 문제로 문자 접수가 거절되었습니다. 관리자에게 문의해 주세요.',
    'provider_balance': '발송 서비스 잔액 문제로 문자 접수가 거절되었습니다. 관리자에게 문의해 주세요.',
    'provider_sender': '발신번호 등록 또는 이용 제한 문제로 문자 접수가 거절되었습니다. 관리자에게 문의해 주세요.',
    'request_invalid': '발송 서비스가 문자 형식 또는 내용 문제로 접수를 거절했습니다. 관리자에게 문의해 주세요.',
    'provider_rate_limit': '발송 서비스 요청 한도로 문자 접수가 거절되었습니다. 관리자에게 문의해 주세요.',
    'provider_duplicate': '발송 서비스가 중복 요청으로 문자 접수를 거절했습니다. 재발송하지 말고 발송 내역을 확인해 주세요.',
}


def _safe_provider_code(value):
    return value if type(value) is str and value in _PROVIDER_CODES else 'unclassified'


def _failed_provider_code(messages):
    # We send exactly one message. Ambiguous/mixed lists are never guessed.
    if isinstance(messages, (list, tuple)) and len(messages) == 1:
        return _safe_provider_code(getattr(messages[0], 'status_code', None))
    return 'unclassified'


def _delivery_failure(delivery_status, category, stage, provider_code='unclassified'):
    diagnostic_id = 'SMS-' + uuid.uuid4().hex[:12]
    record = dict(event='sms_delivery_failure', diagnostic_id=diagnostic_id,
                  delivery_status=delivery_status, category=category, stage=stage,
                  provider_code=_safe_provider_code(provider_code))
    try:
        logging.getLogger('sms_delivery').warning(json.dumps(record, sort_keys=True))
    except Exception:
        # A broken log sink must not expose its exception or cause a resend.
        pass
    message = _FAILURE_MESSAGES[delivery_status]
    if delivery_status == 'rejected':
        message = _REJECTION_MESSAGES.get(category, message)
    return SmsDeliveryError(f'{message} 확인번호: {diagnostic_id}',
                            delivery_status=delivery_status,
                            diagnostic_id=diagnostic_id, category=category)


def _send_live(recipient, text):
    # Separate local preparation from provider processing. A response parsing
    # error can happen AFTER acceptance, so never treat it as safe to retry.
    try:
        import httpx
        from pydantic import ValidationError
        from solapi import SolapiMessageService
        from solapi.error.MessageNotReceiveError import MessageNotReceivedError
        from solapi.model import RequestMessage
        api_key, api_secret, sender = _solapi_settings()
        if not all((api_key, api_secret, sender)):
            raise SmsConfigurationError("Solapi configuration is incomplete")
        service = SolapiMessageService(
            api_key=api_key,
            api_secret=api_secret,
        )
        message = RequestMessage(from_=sender, to=recipient, text=text)
    except Exception:
        raise _delivery_failure('not_sent', 'setup_error', 'setup') from None

    try:
        response = service.send(message)
    except MessageNotReceivedError as error:
        code = _failed_provider_code(error.failed_messages)
        raise _delivery_failure('rejected', _PROVIDER_CODES.get(code, 'provider_rejected'),
                                'send', code) from None
    except (TimeoutError, httpx.TimeoutException):
        raise _delivery_failure('unknown', 'network_timeout', 'send') from None
    except httpx.TransportError:
        raise _delivery_failure('unknown', 'network_error', 'send') from None
    except ValidationError:
        raise _delivery_failure('unknown', 'response_invalid', 'response') from None
    except Exception as error:
        # SDK 5.x reports HTTP 4xx as Exception(errorCode, errorMessage).
        # Recognize only exact reviewed codes; never stringify either argument.
        code = _safe_provider_code(error.args[0]) if type(error) is Exception and len(error.args) == 2 else 'unclassified'
        if code != 'unclassified':
            raise _delivery_failure('rejected', _PROVIDER_CODES[code], 'send', code) from None
        raise _delivery_failure('unknown', 'provider_error', 'send') from None

    try:
        if response.failed_message_list or response.group_info.count.registered_success != 1:
            raise ValueError('Unexpected acceptance counts')
        group_id = response.group_info.group_id
        if not isinstance(group_id, str) or not group_id.strip():
            raise ValueError('Missing acceptance identifier')
    except Exception:
        raise _delivery_failure('unknown', 'response_invalid', 'response') from None
    return {'status': 'accepted', 'provider': 'solapi', 'message_group_id': group_id}
