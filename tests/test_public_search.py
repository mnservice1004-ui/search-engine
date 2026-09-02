import json
from pathlib import Path

from app import search_public_tasks
from public_guidance import (
    EXPECTED_TASK_IDS,
    build_public_search_tasks,
    build_public_suggestion_tasks,
    load_public_guidance,
)
from search_engine import search_tasks


ROOT = Path(__file__).resolve().parents[1]
TASKS_PATH = ROOT / "data" / "tasks.json"
GUIDANCE_PATH = ROOT / "data" / "public_guidance.json"
H002_APPROVED_QUERIES = (
    "만성질환 위험군 건강관리",
    "만성질환 건강관리",
    "운동 영양 상담",
    "만성질환 건강상담",
)
H002_INTERNAL_ONLY_QUERIES = ("인바디", "13주", "13주 프로그램")
A007_PUBLIC_QUERIES = (
    "방역·소독 문의",
    "위생해충 방제",
    "소독 의무시설 서류",
    "소독업 신고",
)
SECOND_READY_PUBLIC_TERMS = {
    "A003": (
        "보건증·건강진단서 발급이 필요하신가요?",
        "보건증 발급 방법 문의",
        "건강진단결과서 받는 방법",
        "건강진단서 발급 준비",
        "외국인 결핵검진 확인서 발급",
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
}


def _raw_tasks():
    return json.loads(TASKS_PATH.read_text(encoding="utf-8"))


def _guidance():
    return load_public_guidance(GUIDANCE_PATH)


def test_guided_candidates_use_only_public_title_and_public_search_terms():
    raw_tasks = _raw_tasks()
    guidance = _guidance()
    projected = build_public_search_tasks(raw_tasks, guidance)

    assert len(projected) == 63
    assert len({task["id"] for task in projected}) == 63
    by_id = {task["id"]: task for task in projected}
    for task_id in EXPECTED_TASK_IDS:
        candidate = by_id[task_id]
        terms = guidance[task_id]["public_search_terms"]
        assert set(candidate) == {"id", "name", "priority", "aliases"}
        assert candidate["name"] == guidance[task_id]["public_title"]
        assert [alias["text"] for alias in candidate["aliases"]] == terms
        assert all(alias["type"] == "public" for alias in candidate["aliases"])

    h002_candidate = json.dumps(by_id["H002"], ensure_ascii=False)
    assert "인바디" not in h002_candidate
    assert "13주" not in h002_candidate


def test_all_public_titles_and_terms_rank_the_expected_task_first():
    guidance = _guidance()
    searchable = build_public_search_tasks(_raw_tasks(), guidance)

    for task_id, item in guidance.items():
        for query in item["public_search_terms"]:
            ranked = search_public_tasks(searchable, query, 10)
            assert ranked, (task_id, query)
            assert ranked[0]["id"] == task_id, (task_id, query, ranked[0]["id"])
            assert len(ranked) <= 10
            assert len({task["id"] for task in ranked}) == len(ranked)


def test_a007_public_queries_rank_a007_first_without_internal_aliases():
    guidance = _guidance()
    searchable = build_public_search_tasks(_raw_tasks(), guidance)

    assert len(guidance["A007"]["public_search_terms"]) == 4
    for query in A007_PUBLIC_QUERIES:
        ranked = search_public_tasks(searchable, query, 10)
        assert ranked
        assert ranked[0]["id"] == "A007"


def test_second_ready_fourteen_public_terms_rank_the_expected_task_first():
    guidance = _guidance()
    searchable = build_public_search_tasks(_raw_tasks(), guidance)

    assert sum(len(terms) for terms in SECOND_READY_PUBLIC_TERMS.values()) == 14
    assert not {"A002", "A004", "A008", "F101", "F106", "F204", "R006"} & set(
        guidance
    )
    for task_id, terms in SECOND_READY_PUBLIC_TERMS.items():
        assert tuple(guidance[task_id]["public_search_terms"]) == terms
        for query in terms:
            ranked = search_public_tasks(searchable, query, 10)
            assert ranked, (task_id, query)
            assert ranked[0]["id"] == task_id, (task_id, query, ranked[0]["id"])


def test_h002_approved_terms_rank_first_and_internal_only_terms_do_not_match():
    searchable = build_public_search_tasks(_raw_tasks(), _guidance())

    for query in H002_APPROVED_QUERIES:
        assert search_public_tasks(searchable, query, 10)[0]["id"] == "H002"

    for query in H002_INTERNAL_ONLY_QUERIES:
        assert "H002" not in {
            task["id"] for task in search_public_tasks(searchable, query, 10)
        }


def test_suggestion_candidates_never_include_internal_aliases():
    guidance = _guidance()
    suggestions = build_public_suggestion_tasks(_raw_tasks(), guidance)

    assert len(suggestions) == 63
    for candidate in suggestions:
        if candidate["id"] in EXPECTED_TASK_IDS:
            assert [alias["text"] for alias in candidate["aliases"]] == (
                guidance[candidate["id"]]["public_search_terms"]
            )
        else:
            assert candidate["aliases"] == []


def test_unregistered_task_name_and_alias_rankings_are_unchanged():
    raw_tasks = _raw_tasks()
    guidance = _guidance()
    unregistered = [
        task for task in raw_tasks if task["id"] not in EXPECTED_TASK_IDS
    ]
    searchable = build_public_search_tasks(raw_tasks, guidance)

    assert len(unregistered) == 45
    for task in unregistered:
        queries = [task["name"], *[alias["text"] for alias in task["aliases"]]]
        for query in queries:
            baseline = search_tasks(unregistered, query, 100)
            projected = [
                item
                for item in search_public_tasks(searchable, query, 100)
                if item["id"] not in EXPECTED_TASK_IDS
            ]
            assert [item["id"] for item in projected] == [
                item["id"] for item in baseline
            ], (task["id"], query)
            assert task["id"] in {item["id"] for item in projected}
