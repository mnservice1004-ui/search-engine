import json
from pathlib import Path

from search_engine import normalize, score_task, search_tasks


ROOT = Path(__file__).resolve().parents[1]


def tasks():
    return json.loads((ROOT / "data" / "tasks.json").read_text(encoding="utf-8"))


def test_normalize():
    assert normalize("사전 연명-의료") == "사전연명의료"


def test_expected_result_first():
    result = search_tasks(tasks(), "연명치료")
    assert result
    assert result[0]["id"] == "R003"


def test_unknown_query_returns_zero():
    assert search_tasks(tasks(), "완전히없는검색어") == []


def test_priority_alone_does_not_match():
    sample = {"name": "금연", "priority": 99, "aliases": []}
    assert score_task(sample, "난임지원") == 0


def test_reference_data_counts():
    items = tasks()
    assert len(items) == 63
    assert sum(len(item.get("aliases", [])) for item in items) == 316
    assert len({item["id"] for item in items}) == 63


def test_every_task_has_a_map_point():
    map_points = json.loads((ROOT / "data" / "map_points.json").read_text(encoding="utf-8"))
    missing = []
    for task in tasks():
        points = map_points.get(task.get("floor"), {})
        place = str(task.get("place") or "")
        matched = place in points or any(
            name != "start" and (place in name or name in place)
            for name in points
        )
        if not matched:
            missing.append(task["id"])
    assert missing == []
