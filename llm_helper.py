import json
import os
import re

PHONE_OR_EMAIL = re.compile(r"(?:01[016789][- ]?\d{3,4}[- ]?\d{4})|(?:[\w.+-]+@[\w.-]+)")
SAFE_KEYWORDS = re.compile(r"^[A-Za-z가-힣\s]{2,20}$")
IDENTITY_TERMS = {
    "이름", "성명", "주소", "주민", "생년", "전화", "연락처", "환자명",
    "우리엄마", "우리아빠", "우리아이", "남편", "아내",
}


def expand_query(query):
    if os.getenv("ENABLE_LLM", "false").lower() != "true":
        return []

    raw = str(query or "").strip()
    if PHONE_OR_EMAIL.search(raw):
        return []
    sanitized = " ".join(raw.split())
    if not SAFE_KEYWORDS.fullmatch(sanitized):
        return []
    if len(sanitized.split()) > 4 or any(term in sanitized.replace(" ", "") for term in IDENTITY_TERMS):
        return []

    from openai import OpenAI

    client = OpenAI()
    try:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5.6"),
            instructions=(
                "보건소 민원 검색어를 돕는 보조기다. 의료 조언이나 담당부서·전화번호를 만들지 말고, "
                "입력과 의미가 가까운 짧은 한국어 검색표현을 최대 5개 JSON 문자열 배열로만 반환하라."
            ),
            input=sanitized,
            store=False,
        )
        values = json.loads(response.output_text)
    except Exception:
        return []

    if not isinstance(values, list):
        return []
    cleaned = []
    for value in values:
        text = str(value).strip()
        if 2 <= len(text) <= 30 and PHONE_OR_EMAIL.search(text) is None:
            cleaned.append(text)
    return cleaned[:5]
