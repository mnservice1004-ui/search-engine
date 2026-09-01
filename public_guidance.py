import json
import re
import unicodedata
from datetime import date
from pathlib import Path

from search_engine import normalize as normalize_search_value


SCHEMA_VERSION = 2
DEFAULT_PUBLIC_GUIDANCE_PATH = (
    Path(__file__).resolve().parent / "data" / "public_guidance.json"
)
EXPECTED_TASK_IDS = {
    "A001",
    "A011",
    "A012",
    "A019",
    "H001",
    "H002",
    "M002",
    "M003",
    "M004",
    "M005",
    "M006",
    "M008",
    "R002",
}
PUBLIC_TEXT_FIELDS = (
    "public_title",
    "public_summary",
    "eligibility",
    "documents",
    "fee",
    "operating_hours",
    "visit_steps",
    "public_caution",
    "primary_action",
    "verified_date",
)
PUBLIC_CONTACT_FIELDS = (
    "phone",
    "display_phone",
    "purpose",
    "role",
    "condition",
    "verified_date",
    "is_primary",
)
PUBLIC_SEARCH_TERMS_FIELD = "public_search_terms"
MIN_PUBLIC_SEARCH_TERMS = 2
MAX_PUBLIC_SEARCH_TERMS = 6
MAX_PUBLIC_SEARCH_TERM_LENGTH = 80
TASK_KEYS = {
    "task_id",
    *PUBLIC_TEXT_FIELDS,
    PUBLIC_SEARCH_TERMS_FIELD,
    "organization",
    "location",
}
ORGANIZATION_KEYS = {"department", "team"}
LOCATION_KEYS = {"floor", "room", "route_text", "show_map"}
NULLABLE_PUBLIC_TEXT_FIELDS = {"documents", "fee", "operating_hours"}
PHONE_RUN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:tel\s*:\s*)?(?:\+|\()?\d"
    r"(?:[\d\s().:+/\-]{1,32}\d)?(?![A-Za-z0-9])",
    re.IGNORECASE,
)
CONTEXT_PHONE_RE = re.compile(
    r"(?:전화|문의|연락처|대표번호|내선|콜센터|phone|tel)\s*:?[\s]*"
    r"((?:\+|\()?\d(?:[\d\s().+/\-]{1,32}\d)?)",
    re.IGNORECASE,
)
UNSAFE_CONTACT_VALUE_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\|/(?:home|users|private|tmp)/|"
    r"review|raw|source|local[_ -]?path|sha[- ]?256|"
    r"confirmed|ambiguous|conflict|unmatched|probable[_ -]?review|"
    r"원문\s*행|검수|검토|관리자|검수자|내부\s*(?:메모|자료|경로|상태))",
    re.IGNORECASE,
)
HEX_DIGEST_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", re.IGNORECASE)
TASK_ID_SEARCH_TERM_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]\d{3}(?![A-Za-z0-9])")
EMPLOYEE_SEARCH_TERM_RE = re.compile(
    r"(?:(?:담당자|직원|주무관|팀장|과장)\s*(?:이름|성명|[가-힣]{2,4})|"
    r"[가-힣]{2,4}\s*(?:담당자|직원|주무관|팀장|과장))",
    re.IGNORECASE,
)
H002_FORBIDDEN_SEARCH_TERM_RE = re.compile(
    r"(?:인바디|13\s*주|근로자|무료)",
    re.IGNORECASE,
)


class PublicGuidanceConfigurationError(RuntimeError):
    """Raised when versioned public guidance is missing or invalid."""


def _reject_duplicate_json_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise PublicGuidanceConfigurationError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _normalize_phone_scan_text(value):
    normalized = unicodedata.normalize("NFKC", value)
    characters = []
    for character in normalized:
        category = unicodedata.category(character)
        if category == "Cf":
            continue
        if character.isspace() or category.startswith("Z"):
            characters.append(" ")
            continue
        if category == "Pd" or character == "−":
            characters.append("-")
            continue
        try:
            characters.append(str(unicodedata.decimal(character)))
        except (TypeError, ValueError):
            characters.append(character)
    return re.sub(r" +", " ", "".join(characters))


def _phone_digits(value):
    return "".join(
        character
        for character in value
        if character.isascii() and character.isdigit()
    )


def _is_phone_like_run(run):
    value = run.strip()
    digits = _phone_digits(value)
    if not digits:
        return False
    if value.casefold().startswith("tel"):
        return 4 <= len(digits) <= 15
    if value.startswith("+"):
        return 8 <= len(digits) <= 15
    if digits.startswith("0082"):
        return 10 <= len(digits) <= 15
    if re.match(r"^82[\s.(/\-]", value) and 10 <= len(digits) <= 13:
        return True
    if digits.startswith("0") and 9 <= len(digits) <= 12:
        return True
    return len(digits) == 8 and re.fullmatch(r"1(?:5|6|8)\d{6}", digits) is not None


def _contains_phone_like(value):
    normalized = _normalize_phone_scan_text(value)
    for match in CONTEXT_PHONE_RE.finditer(normalized):
        digit_count = len(_phone_digits(match.group(1)))
        if 4 <= digit_count <= 15:
            return True
    return any(
        _is_phone_like_run(match.group(0))
        for match in PHONE_RUN_RE.finditer(normalized)
    )


def _reject_embedded_phone_numbers(value, label="root"):
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_embedded_phone_numbers(item, f"{label}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_embedded_phone_numbers(item, f"{label}[{index}]")
    elif isinstance(value, str) and _contains_phone_like(value):
        raise PublicGuidanceConfigurationError(
            f"phone-like value is not allowed at {label}"
        )


def _require_exact_keys(value, expected, label):
    if not isinstance(value, dict):
        raise PublicGuidanceConfigurationError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        unknown = sorted(actual - expected)
        missing = sorted(expected - actual)
        raise PublicGuidanceConfigurationError(
            f"{label} has invalid keys; unknown={unknown}, missing={missing}"
        )


def _require_text(value, label, *, nullable=False):
    if value is None and nullable:
        return
    if not isinstance(value, str) or not value.strip():
        raise PublicGuidanceConfigurationError(f"{label} must be non-empty text")


def _normalize_public_search_term(value):
    return normalize_search_value(value)


def _validate_public_search_terms(item, label):
    terms = item[PUBLIC_SEARCH_TERMS_FIELD]
    terms_label = f"{label}.{PUBLIC_SEARCH_TERMS_FIELD}"
    if not isinstance(terms, list):
        raise PublicGuidanceConfigurationError(f"{terms_label} must be an array")
    if not MIN_PUBLIC_SEARCH_TERMS <= len(terms) <= MAX_PUBLIC_SEARCH_TERMS:
        raise PublicGuidanceConfigurationError(
            f"{terms_label} must contain {MIN_PUBLIC_SEARCH_TERMS} to "
            f"{MAX_PUBLIC_SEARCH_TERMS} terms"
        )

    normalized_terms = set()
    for term_index, term in enumerate(terms):
        term_label = f"{terms_label}[{term_index}]"
        if not isinstance(term, str) or not term.strip():
            raise PublicGuidanceConfigurationError(
                f"{term_label} must be non-empty text"
            )
        normalized = _normalize_public_search_term(term)
        if len(normalized) > MAX_PUBLIC_SEARCH_TERM_LENGTH:
            raise PublicGuidanceConfigurationError(
                f"{term_label} exceeds the maximum length"
            )
        if normalized in normalized_terms:
            raise PublicGuidanceConfigurationError(
                f"{term_label} duplicates another search term"
            )
        if (
            _contains_phone_like(term)
            or HEX_DIGEST_RE.search(normalized)
            or UNSAFE_CONTACT_VALUE_RE.search(normalized)
            or TASK_ID_SEARCH_TERM_RE.search(normalized.upper())
            or EMPLOYEE_SEARCH_TERM_RE.search(normalized)
        ):
            raise PublicGuidanceConfigurationError(
                f"unsafe public search term at {term_label}"
            )
        if (
            item["task_id"] == "H002"
            and H002_FORBIDDEN_SEARCH_TERM_RE.search(normalized)
        ):
            raise PublicGuidanceConfigurationError(
                f"unverified public search term at {term_label}"
            )
        normalized_terms.add(normalized)

    if item["public_title"] not in terms:
        raise PublicGuidanceConfigurationError(
            f"{terms_label} must include public_title"
        )


def _validate_guidance_item(item, index):
    label = f"tasks[{index}]"
    _require_exact_keys(item, TASK_KEYS, label)
    _require_text(item["task_id"], f"{label}.task_id")
    for field in PUBLIC_TEXT_FIELDS:
        _require_text(
            item[field],
            f"{label}.{field}",
            nullable=field in NULLABLE_PUBLIC_TEXT_FIELDS,
        )
        if isinstance(item[field], str) and _contains_phone_like(item[field]):
            raise PublicGuidanceConfigurationError(
                f"phone-like value is not allowed at {label}.{field}"
            )
    _validate_public_search_terms(item, label)
    try:
        date.fromisoformat(item["verified_date"])
    except ValueError as error:
        raise PublicGuidanceConfigurationError(
            f"{label}.verified_date must use YYYY-MM-DD"
        ) from error

    organization = item["organization"]
    _require_exact_keys(organization, ORGANIZATION_KEYS, f"{label}.organization")
    _require_text(
        organization["department"], f"{label}.organization.department"
    )
    _require_text(
        organization["team"], f"{label}.organization.team", nullable=True
    )

    location = item["location"]
    _require_exact_keys(location, LOCATION_KEYS, f"{label}.location")
    _require_text(location["floor"], f"{label}.location.floor", nullable=True)
    _require_text(location["room"], f"{label}.location.room", nullable=True)
    _require_text(location["route_text"], f"{label}.location.route_text")
    if not isinstance(location["show_map"], bool):
        raise PublicGuidanceConfigurationError(
            f"{label}.location.show_map must be a boolean"
        )
    if location["show_map"]:
        if location["floor"] is None or location["room"] is None:
            raise PublicGuidanceConfigurationError(
                f"{label}.location requires floor and room when show_map is true"
            )
    elif location["floor"] is not None or location["room"] is not None:
        raise PublicGuidanceConfigurationError(
            f"{label}.location cannot include floor or room when show_map is false"
        )


def load_public_guidance(path=None):
    path = DEFAULT_PUBLIC_GUIDANCE_PATH if path is None else Path(path)
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except FileNotFoundError as error:
        raise PublicGuidanceConfigurationError(
            f"public guidance file is missing: {path}"
        ) from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PublicGuidanceConfigurationError(
            f"public guidance file cannot be read: {path}"
        ) from error

    _reject_embedded_phone_numbers(payload)
    _require_exact_keys(payload, {"schema_version", "tasks"}, "root")
    if type(payload["schema_version"]) is not int or (
        payload["schema_version"] != SCHEMA_VERSION
    ):
        raise PublicGuidanceConfigurationError(
            f"schema_version must be {SCHEMA_VERSION}"
        )
    if not isinstance(payload["tasks"], list):
        raise PublicGuidanceConfigurationError("root.tasks must be an array")

    guidance = {}
    for index, item in enumerate(payload["tasks"]):
        _validate_guidance_item(item, index)
        task_id = item["task_id"]
        if task_id in guidance:
            raise PublicGuidanceConfigurationError(f"duplicate task_id: {task_id}")
        guidance[task_id] = item
    if set(guidance) != EXPECTED_TASK_IDS:
        expected = ", ".join(sorted(EXPECTED_TASK_IDS))
        raise PublicGuidanceConfigurationError(
            f"public guidance must contain exactly: {expected}"
        )
    return guidance


def _safe_contact_text(value, *, fallback=None):
    if value is None:
        return fallback
    if not isinstance(value, str):
        return fallback
    text = value.strip()
    if not text:
        return fallback
    if (
        HEX_DIGEST_RE.search(text)
        or UNSAFE_CONTACT_VALUE_RE.search(text)
    ):
        return fallback
    return text


def _public_contact(contact, task_id):
    public_contact = {
        "phone": contact.get("phone"),
        "display_phone": contact.get("display_phone"),
        "purpose": _safe_contact_text(contact.get("purpose"), fallback="연락처"),
        "role": _safe_contact_text(contact.get("role")),
        "condition": _safe_contact_text(contact.get("condition")),
        "verified_date": contact.get("verified_date"),
        "is_primary": bool(contact.get("is_primary")),
    }
    if task_id == "R002":
        if public_contact["is_primary"]:
            public_contact.update(
                purpose="대표전화",
                role="어르신 건강관리 문의",
                condition=None,
            )
        else:
            public_contact.update(
                purpose="권역별 방문건강 문의",
                role=None,
                condition="담당 지역은 대표전화로 확인해 주세요.",
            )
    return public_contact


def _guided_search_task(task, guidance):
    """Return the only candidate fields allowed to rank a guided task."""

    return {
        "id": str(task.get("id") or ""),
        "name": guidance["public_title"],
        "priority": int(task.get("priority") or 0),
        "aliases": [
            {"text": term, "weight": 12, "type": "public"}
            for term in guidance[PUBLIC_SEARCH_TERMS_FIELD]
        ],
    }


def build_public_search_tasks(tasks, guidance_by_task):
    """Separate guided public candidates from unregistered legacy candidates."""

    projected = []
    for task in tasks:
        task_id = str(task.get("id") or "")
        guidance = guidance_by_task.get(task_id)
        projected.append(
            _guided_search_task(task, guidance) if guidance else task
        )
    return projected


def build_public_suggestion_tasks(tasks, guidance_by_task):
    """Keep internal aliases out of suggestion responses."""

    projected = []
    for task in tasks:
        task_id = str(task.get("id") or "")
        guidance = guidance_by_task.get(task_id)
        if guidance:
            projected.append(_guided_search_task(task, guidance))
        else:
            projected.append(
                {
                    "id": task_id,
                    "name": task.get("name"),
                    "priority": int(task.get("priority") or 0),
                    "aliases": [],
                }
            )
    return projected


def serialize_public_task(task, contacts, guidance_by_task):
    """Build a public task from an explicit allowlist after ranking is complete."""

    task_id = str(task.get("id") or "")
    guidance = guidance_by_task.get(task_id)
    public_contacts = [
        _public_contact(contact, task_id) for contact in contacts or []
    ]
    primary_contact = next(
        (contact for contact in public_contacts if contact["is_primary"]),
        None,
    )

    if guidance:
        organization = guidance["organization"]
        location = guidance["location"]
        public_text = {field: guidance[field] for field in PUBLIC_TEXT_FIELDS}
        name = guidance["public_title"]
        department = organization["department"]
        team = organization["team"]
        floor = location["floor"]
        room = location["room"]
        route = location["route_text"]
        show_map = location["show_map"]
        question = guidance["eligibility"]
        caution = guidance["public_caution"]
        script = guidance["public_summary"]
        location_condition = ""
    else:
        public_text = {field: None for field in PUBLIC_TEXT_FIELDS}
        name = task.get("name")
        department = task.get("department")
        team = task.get("team")
        floor = task.get("floor")
        room = task.get("place")
        route = task.get("route")
        show_map = bool(floor and room)
        question = task.get("question")
        caution = task.get("caution")
        script = task.get("script")
        location_condition = task.get("location_condition") or task.get(
            "locationCondition"
        ) or ""

    result = {
        "id": task_id,
        "name": name,
        "department": department,
        "team": team,
        "floor": floor,
        "place": room,
        "room": room,
        "route": route,
        "show_map": show_map,
        "question": question,
        "caution": caution,
        "script": script,
        "location_condition": location_condition,
        "locationCondition": location_condition,
        "aliases": (
            list(guidance[PUBLIC_SEARCH_TERMS_FIELD]) if guidance else []
        ),
        "primary_contact": primary_contact,
        "contacts": public_contacts,
        **public_text,
    }
    if "score" in task:
        result["score"] = task.get("score")
    return result
