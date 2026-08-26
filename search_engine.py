import re
import unicodedata


PUNCTUATION_RE = re.compile(r"[\s·ㆍ\-_/()\[\]{}.,:;?!'\"“”‘’]")
TOKEN_RE = re.compile(r"[^0-9a-zA-Z가-힣]+")


def normalize(value):
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return PUNCTUATION_RE.sub("", text)


def tokens(value):
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return [token for token in TOKEN_RE.sub(" ", text).split() if len(token) >= 2]


def _candidate_map(task):
    raw_candidates = [
        (task.get("name"), 13),
        (task.get("representative"), 11),
        (task.get("place"), 9),
        (f'{task.get("floor", "")}{task.get("place", "")}', 10),
        (task.get("department"), 5),
        (task.get("team"), 6),
    ]
    raw_candidates.extend(
        (alias.get("text"), int(alias.get("weight", 1)))
        for alias in task.get("aliases", [])
    )

    # 같은 표현이 업무명·별칭에 중복되어도 한 번만 점수화한다.
    deduped = {}
    for text, weight in raw_candidates:
        key = normalize(text)
        if key:
            deduped[key] = max(weight, deduped.get(key, 0))
    return deduped


def score_task(task, raw_query):
    query_norm = normalize(raw_query)
    query_tokens = tokens(raw_query)
    if len(query_norm) < 2:
        return 0

    match_score = 0
    for candidate_norm, weight in _candidate_map(task).items():
        if query_norm == candidate_norm:
            match_score += 180 + weight * 8 + len(candidate_norm)
        elif query_norm in candidate_norm:
            match_score += weight * 11 + min(len(query_norm), 25)
        elif candidate_norm in query_norm:
            match_score += weight * 14 + min(len(candidate_norm), 30)

    blob = normalize(" ".join(str(task.get(field, "")) for field in (
        "name", "representative", "department", "team", "floor", "place",
        "route", "question", "caution", "script", "locationCondition",
        "location_condition",
    )) + " " + " ".join(alias.get("text", "") for alias in task.get("aliases", [])))

    token_hits = 0
    for token in query_tokens:
        token_norm = normalize(token)
        if len(token_norm) >= 2 and token_norm in blob:
            match_score += min(len(token_norm), 10) * 5
            token_hits += 1
    if len(query_tokens) >= 2 and token_hits == len(query_tokens):
        match_score += 30

    # 중요: 실제 일치가 없으면 priority만으로 결과를 만들지 않는다.
    if match_score == 0:
        return 0
    return match_score + int(task.get("priority", 0))


def search_tasks(tasks, query, limit=10):
    ranked = []
    for task in tasks:
        score = score_task(task, query)
        if score > 0:
            ranked.append({**task, "score": score})
    ranked.sort(key=lambda item: (-item["score"], -int(item.get("priority", 0)), item.get("name", "")))
    return ranked[: max(1, min(int(limit), 100))]


def suggest_terms(tasks, query, limit=8):
    query_norm = normalize(query)
    if len(query_norm) < 1:
        return []
    candidates = {}
    for task in tasks:
        values = [(task.get("name", ""), 13)] + [
            (alias.get("text", ""), int(alias.get("weight", 1)))
            for alias in task.get("aliases", [])
        ]
        for text, weight in values:
            text_norm = normalize(text)
            if query_norm in text_norm:
                candidates[text] = max(weight, candidates.get(text, 0))
    return [text for text, _ in sorted(candidates.items(), key=lambda item: (-item[1], len(item[0]), item[0]))[:limit]]
