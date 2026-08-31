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
    primary_contact = task.get("primary_contact") or {}
    phone = str(
        primary_contact.get("display_phone") or primary_contact.get("phone") or ""
    ).strip()
    if not phone:
        raise ValueError("공식 담당 연락처가 아직 등록되지 않았습니다.")
    title = task.get("public_title") or task.get("name") or "보건민원 안내"
    summary = task.get("public_summary") or task.get("script")
    route = task.get("route")
    verified_date = task.get("verified_date") or primary_contact.get("verified_date")
    lines = [f"[동탄구보건소 민원안내]", f"업무: {title}"]
    if summary:
        lines.append(f"안내: {summary}")
    if department:
        lines.append(f"문의하는 곳: {department}")
    if route:
        lines.append(f"방문 안내: {route}")
    lines.extend(
        (
            f"전화: {phone}",
            f"확인일: {verified_date or '전화로 확인해 주세요'}",
            "전화번호 연결 여부는 휴대전화 문자 앱에 따라 다를 수 있습니다.",
        )
    )
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
