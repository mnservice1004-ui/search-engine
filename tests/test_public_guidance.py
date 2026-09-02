import copy
import json
from hashlib import sha256
from pathlib import Path

import pytest

from public_guidance import (
    EXPECTED_TASK_IDS,
    PUBLIC_CONTACT_FIELDS,
    PUBLIC_TEXT_FIELDS,
    PublicGuidanceConfigurationError,
    load_public_guidance,
    serialize_public_task,
)
from search_engine import normalize


ROOT = Path(__file__).resolve().parents[1]
GUIDANCE_PATH = ROOT / "data" / "public_guidance.json"
TASKS_PATH = ROOT / "data" / "tasks.json"
NEW_TASK_IDS = {
    "A001",
    "A019",
    "H001",
    "H002",
    "M002",
    "M003",
    "M004",
    "M005",
    "M006",
    "M008",
}
SECOND_READY_TASK_IDS = {"A003", "F103", "F108", "F201"}
DISALLOWED_TASK_IDS = {"A002", "A004", "A008", "F101", "F106", "F204", "R006"}
MAP_LOCATIONS = {
    "A001": ("1층", "진료실"),
    "A003": ("1층", "민원실"),
    "A019": ("1층", "영상의학실"),
    "F103": ("1층", "진료실"),
    "F108": ("1층", "민원실"),
    "F201": ("2층", "만성질환관리센터"),
    "H001": ("2층", "금연상담실"),
    "H002": ("2층", "만성질환관리센터"),
}
NO_MAP_IDS = {"A007", "M002", "M003", "M004", "M005", "M006", "M008", "R002"}
H002_FORBIDDEN_PUBLIC_FRAGMENTS = (
    "인바디",
    "13주",
    "근로자",
    "무료",
    "09:00",
    "18:00",
)
EXPECTED_PUBLIC_SEARCH_TERMS = {
    "A001": (
        "보건소 진료를 받고 싶으신가요?",
        "보건소 진료",
        "일반진료",
        "진료 접수",
        "진료를 받으러 왔어요",
    ),
    "A003": (
        "보건증·건강진단서 발급이 필요하신가요?",
        "보건증 발급 방법 문의",
        "건강진단결과서 받는 방법",
        "건강진단서 발급 준비",
        "외국인 결핵검진 확인서 발급",
    ),
    "A007": (
        "방역·소독 업무를 문의하시나요?",
        "위생해충 방제 문의",
        "소독 의무시설 서류 제출",
        "소독업 신고 준비 안내",
    ),
    "A011": (
        "결핵 상담이나 관리가 필요하신가요?",
        "결핵 상담",
        "결핵 관리",
        "결핵 관련 상담",
    ),
    "A012": (
        "결핵 검사를 받고 싶으신가요?",
        "결핵 검사",
        "결핵 검사 문의",
        "결핵 검사를 받으러 왔어요",
    ),
    "A019": (
        "골다공증 검사를 받고 싶으신가요?",
        "골다공증 검사",
        "골밀도 검사",
        "골밀도 검사 예약",
        "예약한 골다공증 검사",
    ),
    "F103": (
        "진료실을 찾으시나요?",
        "보건소 진료실 찾아가는 길",
        "일반진료 받는 곳 안내",
    ),
    "F108": (
        "민원실을 찾으시나요?",
        "보건소 민원 접수 장소 안내",
        "민원 창구 찾아가는 길",
    ),
    "F201": (
        "만성질환관리센터를 찾으시나요?",
        "보건소 만성질환 상담 장소 안내",
        "건강관리센터 찾아가는 길",
    ),
    "H001": (
        "담배를 끊는 상담을 받고 싶으신가요?",
        "금연 상담",
        "금연클리닉",
        "금연상담 예약",
        "담배 끊기 상담",
    ),
    "H002": (
        "만성질환 위험군 건강관리를 받고 싶으신가요?",
        "만성질환 위험군 건강관리",
        "만성질환 건강관리",
        "운동 영양 상담",
        "만성질환 건강상담",
    ),
    "M002": (
        "아기의 선천성대사이상 지원이 필요하신가요?",
        "선천성대사이상 의료비 지원",
        "선천성대사이상 검사비 지원",
        "선천성대사이상 환아 지원",
        "신생아 선천성대사이상 지원",
    ),
    "M003": (
        "난임 시술비 지원을 신청하고 싶으신가요?",
        "난임 시술비 지원",
        "난임부부 시술비 지원",
        "체외수정 지원",
        "인공수정 지원",
        "난임 시술비 사전신청",
    ),
    "M004": (
        "산모·신생아 건강관리 지원을 신청하고 싶으신가요?",
        "산모 신생아 건강관리",
        "산모 신생아 건강관리 지원",
        "출산가정 방문 건강관리",
        "산후도우미 지원",
    ),
    "M005": (
        "고위험 임산부 의료비 지원이 필요하신가요?",
        "고위험 임산부 의료비 지원",
        "고위험 임신질환 지원",
        "고위험 임산부 의료비",
        "고위험 임신 의료비 지원",
    ),
    "M006": (
        "아기 기저귀·조제분유 지원을 신청하고 싶으신가요?",
        "기저귀 조제분유 지원",
        "기저귀 바우처",
        "조제분유 바우처",
        "아기 기저귀 지원",
        "아기 분유 지원",
    ),
    "M008": (
        "미숙아·선천성이상아 의료비 지원이 필요하신가요?",
        "미숙아 의료비 지원",
        "선천성이상아 의료비 지원",
        "미숙아 선천성이상아 지원",
    ),
    "R002": (
        "65세 이상 건강관리 서비스를 찾으시나요?",
        "65세 이상 건강관리",
        "어르신 건강관리",
        "어르신 오늘 건강",
        "AI·IoT 어르신 건강관리",
        "스마트워치 건강관리",
    ),
}


def write_payload(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def base_payload():
    return json.loads(GUIDANCE_PATH.read_text(encoding="utf-8"))


PHONE_TEST_PATHS = (
    ("tasks", 0, "public_summary"),
    ("tasks", 0, "eligibility"),
    ("tasks", 1, "visit_steps"),
    ("tasks", 1, "public_caution"),
    ("tasks", 2, "primary_action"),
    ("tasks", 2, "organization", "department"),
    ("tasks", 2, "location", "route_text"),
)


BLOCKED_PHONE_LIKE_VALUES = (
    "031-5189-5032",
    "031 5189 5032",
    "031.5189.5032",
    "(031) 5189-5032",
    "03151895032",
    "tel:031-5189-5032",
    "+82-31-5189-5032",
    "+82 31 5189 5032",
    "+82 (0)31 5189 5032",
    "0082-31-5189-5032",
    "+823151895032",
    "82-31-5189-5032",
    "＋８２－３１－５１８９－５０３２",
    "+82–31–5189–5032",
    "+82-31-5189-5032",
    "문의는 +82-31-5189-5032로 해 주세요.",
    "010-1234-5678",
    "+82-10-1234-5678",
    "1588-1234",
    "내선 5032",
    "문의: 5032",
    "031\u200b5189\u20605032",
    "031\u00a05189\u00a05032",
)


ALLOWED_NON_PHONE_VALUES = (
    "2026-08-28",
    "2026.08.28",
    "2026년 8월 28일",
    "20260828",
    "65세 이상 어르신",
    "6개월 동안 건강관리를 받습니다.",
    "13주 건강관리",
    "1,100원",
    "신청기한은 출산일로부터 60일입니다.",
    "평일 09:00~18:00",
    "1층",
    "2층",
    "3층",
    "A011",
    "A012",
    "R002",
    "A001·A019·M002",
    "A011·A012·R002",
    "A011 — 2026-08-28",
    "업무 63건",
    "검색 결과는 최대 10개입니다.",
    "오전 9시부터 오후 6시까지",
    "1:1 건강관리",
    "방문 장소는 전화로 확인해 주세요.",
)


def set_nested(payload, path, value):
    target = payload
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value


def test_checked_in_public_guidance_has_exact_eighteen_task_contract(monkeypatch, tmp_path):
    payload = base_payload()
    guidance = load_public_guidance(GUIDANCE_PATH)

    assert payload["schema_version"] == 2
    assert set(guidance) == EXPECTED_TASK_IDS
    assert len(guidance) == 18
    assert sum(len(item["public_search_terms"]) for item in guidance.values()) == 83
    assert not DISALLOWED_TASK_IDS & set(guidance)
    assert NEW_TASK_IDS <= set(guidance)
    assert SECOND_READY_TASK_IDS <= set(guidance)
    for task_id, item in guidance.items():
        assert item["task_id"] == task_id
        assert set(PUBLIC_TEXT_FIELDS) <= set(item)
        assert tuple(item["public_search_terms"]) == EXPECTED_PUBLIC_SEARCH_TERMS[task_id]
        assert item["public_title"] in item["public_search_terms"]
        assert 2 <= len(item["public_search_terms"]) <= 6
        serialized = json.dumps(item, ensure_ascii=False)
        assert "031-" not in serialized
        for forbidden in ("note", "source", "status", "source_row", "hash", "local_path"):
            assert forbidden not in serialized

    assert guidance["A011"]["public_title"] == "결핵 상담이나 관리가 필요하신가요?"
    assert guidance["A012"]["public_title"] == "결핵 검사를 받고 싶으신가요?"

    a007 = guidance["A007"]
    assert a007["verified_date"] == "2026-08-26"
    assert a007["fee"] is None
    assert a007["operating_hours"] is None
    assert a007["location"] == {
        "floor": None,
        "room": None,
        "route_text": "방문 장소는 전화로 확인해 주세요.",
        "show_map": False,
    }

    r002 = guidance["R002"]
    assert r002["organization"] == {
        "department": "건강증진과",
        "team": "지역보건팀",
    }
    assert r002["location"] == {
        "floor": None,
        "room": None,
        "route_text": "방문 장소는 전화로 확인해 주세요.",
        "show_map": False,
    }
    monkeypatch.chdir(tmp_path)
    assert set(load_public_guidance()) == EXPECTED_TASK_IDS


def test_existing_fourteen_guidance_objects_are_unchanged():
    payload = base_payload()
    existing = [
        item for item in payload["tasks"] if item["task_id"] not in SECOND_READY_TASK_IDS
    ]
    canonical = json.dumps(
        existing,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    assert len(existing) == 14
    assert sha256(canonical).hexdigest() == (
        "5e3a102c6c575b37f9f93a2e250474880ab538e33cbcf37fc8d2f42c5d4fc2a8"
    )


def test_a007_guidance_preserves_verified_scope_and_forbids_unverified_claims():
    item = load_public_guidance(GUIDANCE_PATH)["A007"]
    serialized = json.dumps(item, ensure_ascii=False)

    for expected in (
        "취약지역",
        "위생해충",
        "소독 의무시설",
        "소독업",
        "소독증명서",
        "자율점검표",
        "전화로",
    ):
        assert expected in serialized
    for forbidden in (
        "가정 방역을 해드립니다",
        "직접 방문합니다",
        "무료입니다",
        "준비물이 없습니다",
        "09:00",
        "18:00",
        "상시 접수",
        "당일 처리",
        "3층",
        "보건행정과로 방문",
        "031-",
    ):
        assert forbidden not in serialized


def test_second_ready_guidance_preserves_verified_location_only_boundaries():
    guidance = load_public_guidance(GUIDANCE_PATH)

    a003 = guidance["A003"]
    assert a003["verified_date"] == "2026-08-27"
    assert a003["operating_hours"] is None
    assert "3,000원" in a003["fee"]
    assert "5,000원" in a003["fee"]
    assert "2,000원" in a003["fee"]
    assert "수수료와 준비물은 방문 전에 확인" in a003["public_caution"]

    f103 = guidance["F103"]
    f103_serialized = json.dumps(f103, ensure_ascii=False)
    assert f103["verified_date"] == "2026-08-27"
    assert f103["documents"] is None
    assert f103["fee"] is None
    assert f103["operating_hours"] is None
    assert "현재 이용 가능 여부와 시간을 대표전화로" in f103["primary_action"]
    for forbidden in (
        "화성시민",
        "실물 신분증",
        "평일 오전 9시",
        "접수는 오전",
        "점심시간",
        "토요일",
        "공휴일",
        "본인부담",
    ):
        assert forbidden not in f103_serialized

    f108 = guidance["F108"]
    assert f108["verified_date"] == "2026-08-27"
    assert "준비물과 처리 장소가 다를 수" in f108["public_caution"]
    assert "대표전화로 먼저 확인" in f108["public_caution"]

    f201 = guidance["F201"]
    f201_serialized = json.dumps(f201, ensure_ascii=False)
    assert f201["verified_date"] == "2026-08-27"
    assert f201["documents"] is None
    assert f201["fee"] is None
    assert f201["operating_hours"] is None
    assert "현재 상담·접수 여부를 대표전화로" in f201["primary_action"]
    for forbidden in (
        "13주",
        "인바디",
        "30세",
        "69세",
        "운동처방",
        "영양상담",
        "모집",
    ):
        assert forbidden not in f201_serialized


def test_first_batch_location_policy_uses_only_verified_service_places():
    guidance = load_public_guidance(GUIDANCE_PATH)

    for task_id, (floor, room) in MAP_LOCATIONS.items():
        assert guidance[task_id]["location"] == {
            "floor": floor,
            "room": room,
            "route_text": guidance[task_id]["location"]["route_text"],
            "show_map": True,
        }
        assert floor in guidance[task_id]["location"]["route_text"]
        assert room in guidance[task_id]["location"]["route_text"]

    for task_id in NO_MAP_IDS:
        assert guidance[task_id]["location"] == {
            "floor": None,
            "room": None,
            "route_text": "방문 장소는 전화로 확인해 주세요.",
            "show_map": False,
        }


def test_first_batch_preserves_confirmed_service_boundaries():
    guidance = load_public_guidance(GUIDANCE_PATH)

    assert "예약" in guidance["A019"]["primary_action"]
    assert "6,000원" in guidance["A019"]["fee"]
    assert "검사비는 변동될 수" in guidance["A019"]["public_caution"]
    assert "평일 예약제" in guidance["H001"]["public_caution"]
    assert "30세부터 69세까지" in guidance["H002"]["eligibility"]
    assert "운동·영양 상담" in guidance["H002"]["public_summary"]
    assert guidance["H002"]["fee"] is None
    assert guidance["H002"]["operating_hours"] is None
    assert "만 65세 이상" in guidance["A001"]["fee"]
    assert "검사비와 환아 지원" in guidance["M002"]["public_caution"]
    assert "대상 영아의 부모가" in guidance["M002"]["eligibility"]
    assert "출생일로부터 1년 이내" in guidance["M002"]["eligibility"]
    assert "영아가 신청" not in guidance["M002"]["eligibility"]
    assert "시술 전에" in guidance["M003"]["visit_steps"]
    assert "출산가정을 방문" in guidance["M004"]["public_summary"]
    assert "19개 고위험 임신질환" in guidance["M005"]["eligibility"]
    assert "조제분유" in guidance["M006"]["eligibility"]
    assert "추가 조건" in guidance["M006"]["eligibility"]
    assert guidance["M008"]["fee"] is None
    assert "출생 후 24시간 이내" in guidance["M008"]["eligibility"]
    assert "긴급한 수술이나 치료가 필요" in guidance["M008"]["eligibility"]
    assert "신생아 중환자실(NICU)에 입원" in guidance["M008"]["eligibility"]
    assert "선천성이상아는" in guidance["M008"]["eligibility"]
    assert "2,000백만원" not in json.dumps(guidance["M008"], ensure_ascii=False)
    assert "원문" not in json.dumps(guidance["M008"], ensure_ascii=False)
    assert all(guidance[task_id]["verified_date"] == "2026-08-26" for task_id in NEW_TASK_IDS)


def test_h002_public_guidance_omits_unverified_claims():
    guidance = load_public_guidance(GUIDANCE_PATH)
    serialized = json.dumps(guidance["H002"], ensure_ascii=False)

    assert not any(fragment in serialized for fragment in H002_FORBIDDEN_PUBLIC_FRAGMENTS)


def test_public_search_terms_use_only_the_safe_schema_v2_layer():
    guidance = load_public_guidance(GUIDANCE_PATH)
    all_normalized_terms = []

    for task_id, item in guidance.items():
        normalized = {
            normalize(term)
            for term in item["public_search_terms"]
        }
        assert len(normalized) == len(item["public_search_terms"])
        assert task_id not in item["public_search_terms"]
        all_normalized_terms.extend(normalized)

    assert len(all_normalized_terms) == 83
    assert len(set(all_normalized_terms)) == 83

    h002_terms = " ".join(guidance["H002"]["public_search_terms"])
    for expected in (
        "만성질환 위험군 건강관리",
        "만성질환 건강관리",
        "운동 영양 상담",
        "만성질환 건강상담",
    ):
        assert expected in h002_terms
    assert not any(fragment in h002_terms for fragment in H002_FORBIDDEN_PUBLIC_FRAGMENTS)


def test_guidance_missing_or_invalid_json_fails_closed(tmp_path):
    with pytest.raises(PublicGuidanceConfigurationError, match="missing"):
        load_public_guidance(tmp_path / "missing.json")

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not-json", encoding="utf-8")
    with pytest.raises(PublicGuidanceConfigurationError, match="cannot be read"):
        load_public_guidance(invalid)

    payload = base_payload()
    payload.update({"schema_version": 2.0})
    with pytest.raises(PublicGuidanceConfigurationError):
        load_public_guidance(write_payload(tmp_path / "float-schema.json", payload))


@pytest.mark.parametrize("unsupported_version", (1, 3, True))
def test_unsupported_schema_versions_are_rejected(tmp_path, unsupported_version):
    payload = base_payload()
    payload["schema_version"] = unsupported_version

    with pytest.raises(PublicGuidanceConfigurationError, match="schema_version"):
        load_public_guidance(write_payload(tmp_path / "unsupported-schema.json", payload))


@pytest.mark.parametrize(
    ("mutation", "error_fragment"),
    (
        (lambda item: item.pop("public_search_terms"), "invalid keys"),
        (lambda item: item.update(public_search_terms="결핵 상담"), "must be an array"),
        (lambda item: item.update(public_search_terms=[item["public_title"]]), "must contain"),
        (
            lambda item: item.update(
                public_search_terms=[item["public_title"], *[f"검색어 {index}" for index in range(6)]]
            ),
            "must contain",
        ),
        (
            lambda item: item.update(
                public_search_terms=[item["public_title"], "", "결핵 상담"]
            ),
            "non-empty text",
        ),
        (
            lambda item: item.update(
                public_search_terms=[
                    item["public_title"],
                    "결핵 상담",
                    "  결핵   상담  ",
                ]
            ),
            "duplicates",
        ),
        (
            lambda item: item.update(
                public_search_terms=[
                    item["public_title"],
                    "결핵 상담",
                    "결핵-상담",
                ]
            ),
            "duplicates",
        ),
        (
            lambda item: item.update(
                public_search_terms=[
                    item["public_title"],
                    "ＡＢＣ 건강상담",
                    "ABC 건강상담",
                ]
            ),
            "duplicates",
        ),
        (
            lambda item: item.update(
                public_search_terms=[item["public_title"], "문의: 5032"]
            ),
            "phone-like value",
        ),
        (
            lambda item: item.update(
                public_search_terms=[item["public_title"], "A011"]
            ),
            "unsafe public search term",
        ),
        (
            lambda item: item.update(
                public_search_terms=[item["public_title"], "홍길동 주무관"]
            ),
            "unsafe public search term",
        ),
        (
            lambda item: item.update(
                public_search_terms=[item["public_title"], "source review 상태"]
            ),
            "unsafe public search term",
        ),
        (
            lambda item: item.update(
                public_search_terms=[item["public_title"], "가" * 81]
            ),
            "maximum length",
        ),
        (
            lambda item: item.update(
                public_search_terms=["결핵 상담", "결핵 관리"]
            ),
            "must include public_title",
        ),
    ),
)
def test_invalid_public_search_terms_are_rejected(
    tmp_path, mutation, error_fragment
):
    payload = base_payload()
    mutation(payload["tasks"][0])

    with pytest.raises(PublicGuidanceConfigurationError, match=error_fragment):
        load_public_guidance(write_payload(tmp_path / "invalid-search-terms.json", payload))


@pytest.mark.parametrize("forbidden", ("인바디", "13주", "13주 프로그램", "근로자", "무료"))
def test_h002_rejects_unverified_public_search_terms(tmp_path, forbidden):
    payload = base_payload()
    h002 = next(item for item in payload["tasks"] if item["task_id"] == "H002")
    h002["public_search_terms"][-1] = forbidden

    with pytest.raises(PublicGuidanceConfigurationError, match="unverified") as exc_info:
        load_public_guidance(write_payload(tmp_path / "unsafe-h002-term.json", payload))
    assert forbidden not in str(exc_info.value)


def test_public_search_terms_allow_normal_numbers_and_spacing_variants(tmp_path):
    payload = base_payload()
    r002 = next(item for item in payload["tasks"] if item["task_id"] == "R002")
    r002["public_search_terms"][-1] = "65세 6개월 건강관리 2026-08-28"

    guidance = load_public_guidance(
        write_payload(tmp_path / "safe-number-search-term.json", payload)
    )
    assert guidance["R002"]["public_search_terms"][-1] == (
        "65세 6개월 건강관리 2026-08-28"
    )


@pytest.mark.parametrize("mutation", ("missing", "unapproved"))
def test_guidance_rejects_missing_or_unapproved_task_ids(tmp_path, mutation):
    payload = base_payload()
    if mutation == "missing":
        payload["tasks"].pop()
    else:
        payload["tasks"][-1]["task_id"] = "X999"

    with pytest.raises(PublicGuidanceConfigurationError, match="contain exactly"):
        load_public_guidance(write_payload(tmp_path / f"{mutation}.json", payload))


@pytest.mark.parametrize(
    ("case_index", "phone_like"),
    tuple(enumerate(BLOCKED_PHONE_LIKE_VALUES)),
)
def test_phone_like_values_are_rejected_recursively(tmp_path, case_index, phone_like):
    payload = base_payload()
    path = PHONE_TEST_PATHS[case_index % len(PHONE_TEST_PATHS)]
    set_nested(payload, path, phone_like)

    with pytest.raises(PublicGuidanceConfigurationError) as caught:
        load_public_guidance(write_payload(tmp_path / f"blocked-{case_index}.json", payload))

    message = str(caught.value)
    assert message.startswith("phone-like value is not allowed at root.tasks[")
    assert phone_like not in message
    assert not any(number in message for number in ("5032", "5678", "1234"))


@pytest.mark.parametrize(
    ("case_index", "allowed_value"),
    tuple(enumerate(ALLOWED_NON_PHONE_VALUES)),
)
def test_non_phone_values_are_allowed_recursively(tmp_path, case_index, allowed_value):
    payload = base_payload()
    path = PHONE_TEST_PATHS[case_index % len(PHONE_TEST_PATHS)]
    set_nested(payload, path, allowed_value)

    guidance = load_public_guidance(
        write_payload(tmp_path / f"allowed-{case_index}.json", payload)
    )
    assert set(guidance) == EXPECTED_TASK_IDS


@pytest.mark.parametrize(
    "mutate",
    (
        lambda payload: payload.update({"unexpected": True}),
        lambda payload: payload["tasks"][0].update({"unexpected": True}),
        lambda payload: payload["tasks"].append(copy.deepcopy(payload["tasks"][0])),
        lambda payload: payload.update({"schema_version": True}),
        lambda payload: payload["tasks"][0]["location"].update({"show_map": "yes"}),
        lambda payload: payload["tasks"][2]["location"].update({"floor": "3층"}),
        lambda payload: payload["tasks"][0]["location"].update({"floor": None}),
        lambda payload: payload["tasks"][2]["location"].update({"x": 42}),
        lambda payload: payload["tasks"][0].update({"verified_date": "2026/08/28"}),
    ),
)
def test_guidance_schema_errors_are_rejected(tmp_path, mutate):
    payload = base_payload()
    mutate(payload)

    with pytest.raises(PublicGuidanceConfigurationError):
        load_public_guidance(write_payload(tmp_path / "invalid.json", payload))


def test_duplicate_json_object_key_is_rejected(tmp_path):
    duplicate = GUIDANCE_PATH.read_text(encoding="utf-8").replace(
        '"schema_version": 2,',
        '"schema_version": 2,\n  "schema_version": 2,',
        1,
    )
    path = tmp_path / "duplicate-key.json"
    path.write_text(duplicate, encoding="utf-8")

    with pytest.raises(PublicGuidanceConfigurationError, match="duplicate JSON key"):
        load_public_guidance(path)


def test_unregistered_task_uses_allowlist_instead_of_raw_task_copy():
    raw = {
        "id": "R003",
        "name": "연명치료",
        "department": "건강증진과",
        "team": "지역보건팀",
        "floor": "1층",
        "place": "재활보건실",
        "route": "1층으로 가세요.",
        "question": "문의가 필요한가요?",
        "caution": "전화로 확인해 주세요.",
        "script": "안내를 받으세요.",
        "status": "must-not-leak",
        "source": "must-not-leak",
        "note": "must-not-leak",
        "source_hash": "must-not-leak",
        "local_path": "C:/must-not-leak",
        "review_state": "must-not-leak",
        "raw_payload": {"must": "not leak"},
        "phone": "031-999-9999",
        "aliases": [{"text": "연명치료", "weight": 10, "type": "search"}],
        "score": 321,
    }
    contacts = [
        {
            "phone": "031-5189-0000",
            "display_phone": "031-5189-0000",
            "purpose": "대표전화",
            "role": "문의",
            "condition": None,
            "verified_date": "2026-08-28",
            "is_primary": True,
            "status": "must-not-leak",
            "source_row": 99,
        }
    ]

    item = serialize_public_task(raw, contacts, load_public_guidance(GUIDANCE_PATH))
    serialized = json.dumps(item, ensure_ascii=False)

    assert item["id"] == "R003"
    assert item["score"] == 321
    assert item["show_map"] is True
    assert set(item["contacts"][0]) == set(PUBLIC_CONTACT_FIELDS)
    for forbidden in (
        '"status"',
        '"source"',
        '"note"',
        '"source_hash"',
        '"local_path"',
        '"review_state"',
        '"raw_payload"',
        '"phone": "031-999-9999"',
    ):
        assert forbidden not in serialized


def test_remaining_forty_five_tasks_serialize_without_internal_fallback_or_config_error():
    guidance = load_public_guidance(GUIDANCE_PATH)
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    remaining = [task for task in tasks if task["id"] not in guidance]

    assert len(remaining) == 45
    for raw in remaining:
        item = serialize_public_task(raw, [], guidance)
        serialized = json.dumps(item, ensure_ascii=False)
        assert item["id"] == raw["id"]
        assert item["primary_contact"] is None
        assert item["contacts"] == []
        assert all(item[field] is None for field in PUBLIC_TEXT_FIELDS)
        for forbidden in (
            '"status"',
            '"source"',
            '"note"',
            '"source_hash"',
            '"local_path"',
            '"review_state"',
            '"raw_payload"',
        ):
            assert forbidden not in serialized
