import os
import re

KOREAN_MOBILE = re.compile(r"^01[016789]\d{7,8}$")


def normalize_mobile(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if not KOREAN_MOBILE.fullmatch(digits):
        raise ValueError("휴대전화번호 형식이 올바르지 않습니다.")
    return digits


def build_message(task):
    department = " / ".join(filter(None, [task.get("department"), task.get("team")]))
    contact = " / ".join(filter(None, [task.get("contact_name"), task.get("contact_role")]))
    primary_contact = task.get("primary_contact") or {}
    phone = str(
        primary_contact.get("display_phone") or primary_contact.get("phone") or ""
    ).strip()
    if not phone:
        raise ValueError("공식 담당 연락처가 아직 등록되지 않았습니다.")
    return (
        f'[동탄구보건소 민원안내]\n업무: {task.get("name")}\n'
        f'담당: {department}\n'
        f'담당자/직위: {contact or "공식 확인 필요"}\n'
        f'전화: {phone}\n'
        f'확인일: {primary_contact.get("verified_date") or "공식 확인 필요"}\n'
        "전화번호 연결 여부는 휴대전화 문자 앱에 따라 다를 수 있습니다."
    )


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
