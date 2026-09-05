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


def test_map_targets_anchor_to_printed_floorplan_labels_or_require_review():
    map_points = json.loads((ROOT / "data" / "map_points.json").read_text(encoding="utf-8"))
    targets = [
        point
        for floor_points in map_points.values()
        for name, point in floor_points.items()
        if name not in {"start", "정문"}
    ]

    assert all("map_target_type" in target for target in targets)
    assert all(target["map_target_type"] in {"room", "department"} for target in targets)
    verified = [target for target in targets if target["review_status"] == "verified_floorplan_label"]
    assert all(target["printed_label"] and target["label_bbox"] for target in verified)
    assert all(target["label_bbox"]["top"] > 0 for target in verified)
    assert map_points["3층"]["건강증진과"]["map_target_type"] == "department"
    assert map_points["3층"]["건강증진과"]["printed_label"] == "건강증진과"
    assert map_points["3층"]["소회의실"]["review_status"] == "review_required"
