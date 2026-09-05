import os
import re

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


def build_message(task):
    title = _public_text(task, "public_title")
    if not title:
        raise ValueError("공개 안내가 등록되지 않은 업무는 문자 발송할 수 없습니다.")

    primary_contact = _primary_contact(task) or {}
    phone = str(
        primary_contact.get("display_phone") or primary_contact.get("phone") or ""
    ).strip()
    if not phone:
        raise ValueError("공식 담당 연락처가 아직 등록되지 않았습니다.")
    fields = _selected_sms_fields(task)
    lines = ["[동탄구보건소]", f"업무: {title}"]
    for field in fields:
        value = _sms_field_value(task, field)
        if value:
            lines.append(f"{SMS_FIELD_LABELS[field]}: {value}")
    lines.append(f"문의: {phone}")
    return "\n".join(lines)


def send_contact_sms(task, recipient):
    recipient = normalize_mobile(recipient)
    text = build_message(task)
    mode = os.getenv("SMS_MODE", "mock").lower()
    if mode != "live":
        return {"status": "mocked", "provider": "mock", "preview": text}

    from solapi import SolapiMessageService
    from solapi.model import RequestMessage

    service = SolapiMessageService(
        api_key=os.environ["SOLAPI_API_KEY"],
        api_secret=os.environ["SOLAPI_API_SECRET"],
    )
    message = RequestMessage(
        from_=os.environ["SOLAPI_SENDER"],
        to=recipient,
        text=text,
    )
    response = service.send(message)
    return {
        "status": "accepted",
        "provider": "solapi",
        "message_group_id": response.group_info.group_id,
    }
