import argparse
import csv
import hashlib
import html
import json
import logging
import os
import re
import sqlite3
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / os.getenv("SQLITE_PATH", "data/health_search.db")
TASKS_JSON_PATH = ROOT / "data" / "tasks.json"
REPORT_ROOT = ROOT / "reports" / "contact_matching"

BASE_URL = "https://www.hscity.go.kr"
INDEX_URL = f"{BASE_URL}/health/index.do"
FLOOR_URL = f"{BASE_URL}/health/intro/floorFacilities/dongtanInfo.jsp"
STAFF_URL = f"{BASE_URL}/health/organ/BD_selectHealthOrganList.do?q_healthNm=dongtan"
ALLOWED_HOSTS = {"hscity.go.kr", "www.hscity.go.kr"}
SERVICE_PREFIXES = (
    "/health/business/",
    "/health/medical/",
    "/health/minwon/",
    "/health/vaccination/",
)
GENERAL_FALLBACK_NUMBERS = {"15774200", "0313703900"}
MANAGER_MARKERS = ("과장", "팀장", "소장", "총괄")
INQUIRY_MARKERS = ("문의", "예약", "신청문의", "연락처", "전화")
CURRENT_AFFILIATION = "동탄구보건소"
HISTORICAL_AFFILIATION = "동탄보건소"
PHONE_RE = re.compile(
    r"(?<!\d)(?:"
    r"(?P<short>1[568]\d{2})[-\s]?(?P<short_subscriber>\d{4})|"
    r"(?P<area>0\d{1,2})[-\s)]?(?P<exchange>\d{3,4})[-\s]?(?P<subscriber>\d{4})"
    r")(?!\d)"
)
HEALTH_AFFILIATION_RE = re.compile(
    r"(?:화성시)?(?:만세구|효행구|병점구|동탄구)보건소|"
    r"(?:화성시)?(?:서부|동부|동탄)보건소"
)
EXTERNAL_ORGANIZATION_RE = re.compile(
    r"병원|의원|의료원|대학교|대학병원|질병관리청|공항검역소|보건환경연구원"
)
EXTERNAL_PUBLIC_ORGANIZATION_RE = re.compile(
    r"질병관리청|공항검역소|검역소|보건환경연구원|국립중앙의료원"
)
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")
GENERIC_KEYS = {
    "사업", "업무", "관리", "운영", "지원", "접수", "민원", "상담", "안내",
    "신청", "검사", "위치", "발급", "일반", "관련", "서비스", "센터", "실",
    "건강관리사",
}
KST = timezone(timedelta(hours=9))

CSV_FIELDS = [
    "task_id",
    "task_name",
    "current_department",
    "current_team",
    "current_floor",
    "current_place",
    "previous_phone",
    "candidate_phone",
    "contact_type",
    "official_affiliation",
    "official_position",
    "duty_text_verbatim",
    "service_context_verbatim",
    "source_url",
    "source_page_title",
    "source_page_or_row",
    "source_html_sha256",
    "retrieved_at_kst",
    "matched_keys",
    "match_status",
    "match_reason",
    "alternative_candidates",
    "conflict_note",
    "proposed_action",
    "approved",
    "reviewer_note",
]


class CollectionError(RuntimeError):
    pass


def now_kst():
    return datetime.now(KST).replace(microsecond=0).isoformat()


def clean_text(value):
    lines = []
    for line in html.unescape(str(value or "")).replace("\r", "").split("\n"):
        normalized = re.sub(r"[\t\f\v ]+", " ", line).strip()
        if normalized:
            lines.append(normalized)
    return "\n".join(lines)


def one_line(value):
    return re.sub(r"\s+", " ", clean_text(value)).strip()


def normalize(value):
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"[^0-9a-z가-힣]+", "", text)


def phone_compare(value):
    return re.sub(r"\D", "", str(value or ""))


def phone_occurrences(value):
    """완전 번호와 바로 뒤의 쉼표 축약번호를 원문 위치와 함께 반환한다."""
    text = str(value or "")
    for match in PHONE_RE.finditer(text):
        if match.group("short"):
            display = f"{match.group('short')}-{match.group('short_subscriber')}"
            yield {
                "display": display,
                "comparison": phone_compare(display),
                "start": match.start(),
                "end": match.end(),
                "abbreviated": False,
            }
            continue
        area = match.group("area")
        exchange = match.group("exchange")
        subscriber = match.group("subscriber")
        display = f"{area}-{exchange}-{subscriber}"
        yield {
            "display": display,
            "comparison": phone_compare(display),
            "start": match.start(),
            "end": match.end(),
            "abbreviated": False,
        }
        tail_match = re.match(r"(?P<extensions>(?:\s*[,/]\s*\d{1,4})+)", text[match.end():])
        if not tail_match:
            continue
        extensions = tail_match.group("extensions")
        for extension in re.finditer(r"\d{1,4}", extensions):
            extension_digits = extension.group(0)
            expanded_subscriber = subscriber[:-len(extension_digits)] + extension_digits
            display = f"{area}-{exchange}-{expanded_subscriber}"
            yield {
                "display": display,
                "comparison": phone_compare(display),
                "start": match.end() + extension.start(),
                "end": match.end() + extension.end(),
                "abbreviated": True,
            }


def extract_phones(value):
    found = []
    seen = set()
    for occurrence in phone_occurrences(value):
        display = occurrence["display"]
        comparison = occurrence["comparison"]
        if comparison not in seen:
            seen.add(comparison)
            found.append((display, comparison))
    return found


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_dump(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def validate_official_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
        raise CollectionError(f"공식 HTTPS 범위를 벗어난 URL입니다: {url}")


def canonical_url(url):
    parsed = urlsplit(url)
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def slug_for_url(url):
    parsed = urlsplit(url)
    raw = (parsed.path.strip("/") or "index").replace("/", "_")
    if parsed.query:
        raw += "_" + parsed.query
    slug = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", raw).strip("_")
    return slug[:150] or "source"


class PageParser(HTMLParser):
    BLOCK_TAGS = {
        "address", "article", "aside", "blockquote", "div", "dl", "dt", "dd",
        "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3",
        "h4", "h5", "h6", "header", "li", "main", "nav", "ol", "p", "section",
        "table", "tbody", "thead", "tfoot", "tr", "ul",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.in_title = False
        self.title_parts = []
        self.current_heading_tag = None
        self.current_heading = []
        self.headings = []
        self.current_line = []
        self.lines = []
        self.links = []
        self.in_row = False
        self.current_row = []
        self.in_cell = False
        self.current_cell = []
        self.rows = []

    def _flush_line(self):
        value = clean_text("".join(self.current_line))
        self.current_line = []
        if value:
            self.lines.extend(value.splitlines())

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in self.BLOCK_TAGS or tag == "br":
            self._flush_line()
        if tag == "title":
            self.in_title = True
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.current_heading_tag = tag
            self.current_heading = []
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "tr":
            self.in_row = True
            self.current_row = []
        if tag in {"td", "th"} and self.in_row:
            self.in_cell = True
            self.current_cell = []
        if tag == "br" and self.in_cell:
            self.current_cell.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag == "title":
            self.in_title = False
        if tag in {"td", "th"} and self.in_cell:
            self.current_row.append(clean_text("".join(self.current_cell)))
            self.current_cell = []
            self.in_cell = False
        if tag == "tr" and self.in_row:
            if any(self.current_row):
                self.rows.append(self.current_row)
            self.current_row = []
            self.in_row = False
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            value = one_line("".join(self.current_heading))
            if value:
                self.headings.append({"tag": tag, "text": value})
            self.current_heading_tag = None
            self.current_heading = []
        if tag in self.BLOCK_TAGS:
            self._flush_line()

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
        if self.current_heading_tag:
            self.current_heading.append(data)
        if self.in_cell:
            self.current_cell.append(data)
        self.current_line.append(data)

    def close(self):
        super().close()
        self._flush_line()

    @property
    def title(self):
        return one_line("".join(self.title_parts))

    @property
    def text(self):
        return "\n".join(self.lines)


def parse_page(text):
    parser = PageParser()
    parser.feed(text)
    parser.close()
    return parser


def content_title(parser):
    ignored = {
        "보건소안내", "민원안내", "진료안내", "보건사업안내", "예방접종안내",
        "열린마당", "화성특례시 보건소", "건강증진사업", "지역보건사업",
        "모자보건사업", "감염병관리사업", "의료비지원사업", "치매관리사업",
    }
    for heading in parser.headings:
        if heading["tag"] in {"h3", "h4"} and heading["text"] not in ignored:
            return heading["text"]
    for heading in parser.headings:
        if heading["text"] not in ignored:
            return heading["text"]
    return parser.title or "제목 확인 필요"


@dataclass
class Snapshot:
    kind: str
    requested_url: str
    final_url: str
    page_title: str
    http_status: int
    retrieved_at_kst: str
    html_sha256: str
    page_number: int | None
    raw_path: str
    extraction_success: bool
    error: str
    text: str
    parser: PageParser

    def manifest_record(self):
        return {
            "kind": self.kind,
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "page_title": self.page_title,
            "http_status": self.http_status,
            "retrieved_at_kst": self.retrieved_at_kst,
            "html_sha256": self.html_sha256,
            "page_number": self.page_number,
            "raw_path": self.raw_path,
            "extraction_success": self.extraction_success,
            "error": self.error,
        }


class OfficialFetcher:
    def __init__(self, output_dir, delay, timeout, retries, logger):
        self.output_dir = output_dir
        self.raw_dir = output_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.delay = max(0.1, delay)
        self.timeout = timeout
        self.retries = retries
        self.logger = logger
        self.last_request_at = 0.0
        self.sequence = 0
        self.manifest = []

    def _wait(self):
        remaining = self.delay - (time.monotonic() - self.last_request_at)
        if remaining > 0:
            time.sleep(remaining)

    def fetch(self, url, kind, page_number=None):
        validate_official_url(url)
        last_error = None
        for attempt in range(1, self.retries + 2):
            self._wait()
            self.last_request_at = time.monotonic()
            request = Request(
                url,
                headers={
                    "User-Agent": "DongtanHealthContactAudit/1.0 (+official dry-run; low-rate)",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "ko-KR,ko;q=0.9",
                },
                method="GET",
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    content = response.read()
                    status = int(response.status)
                    final_url = response.geturl()
                    validate_official_url(final_url)
                    charset = response.headers.get_content_charset() or "utf-8"
                text = content.decode(charset, errors="replace")
                parser = parse_page(text)
                retrieved = now_kst()
                digest = sha256_bytes(content)
                self.sequence += 1
                raw_name = f"{self.sequence:03d}_{slug_for_url(final_url)}.html"
                raw_path = self.raw_dir / raw_name
                raw_path.write_bytes(content)
                snapshot = Snapshot(
                    kind=kind,
                    requested_url=url,
                    final_url=final_url,
                    page_title=content_title(parser),
                    http_status=status,
                    retrieved_at_kst=retrieved,
                    html_sha256=digest,
                    page_number=page_number,
                    raw_path=str(raw_path.relative_to(self.output_dir)),
                    extraction_success=True,
                    error="",
                    text=text,
                    parser=parser,
                )
                self.manifest.append(snapshot.manifest_record())
                self.logger.info("HTTP %s %s", status, final_url)
                return snapshot
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self.logger.warning("공식 페이지 요청 실패 %s/%s: %s", attempt, self.retries + 1, last_error)
                if attempt <= self.retries:
                    time.sleep(min(2.0, self.delay * (attempt + 1)))
        record = {
            "kind": kind,
            "requested_url": url,
            "final_url": "",
            "page_title": "",
            "http_status": 0,
            "retrieved_at_kst": now_kst(),
            "html_sha256": "",
            "page_number": page_number,
            "raw_path": "",
            "extraction_success": False,
            "error": last_error or "알 수 없는 오류",
        }
        self.manifest.append(record)
        raise CollectionError(f"공식 페이지를 수집하지 못했습니다: {url} ({record['error']})")


def sqlite_uri(path):
    return f"file:{Path(path).resolve().as_posix()}?mode=ro"


def database_snapshot():
    with sqlite3.connect(sqlite_uri(DB_PATH), uri=True) as connection:
        connection.row_factory = sqlite3.Row
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        task_rows = [dict(row) for row in connection.execute(
            "SELECT * FROM tasks WHERE active=1 ORDER BY id"
        )]
        alias_rows = [dict(row) for row in connection.execute(
            "SELECT task_id, text, weight, type FROM aliases ORDER BY task_id, id"
        )]
        event_count = connection.execute("SELECT COUNT(*) FROM event_logs").fetchone()[0]
    aliases = defaultdict(list)
    for row in alias_rows:
        aliases[row["task_id"]].append({
            "text": row["text"],
            "weight": row["weight"],
            "type": row["type"],
        })
    for task in task_rows:
        task["aliases"] = aliases.get(task["id"], [])
    logical_payload = {
        "tasks": task_rows,
        "aliases": alias_rows,
    }
    logical_hash = sha256_bytes(
        json.dumps(logical_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return {
        "db_path": str(DB_PATH.resolve()),
        "db_size": DB_PATH.stat().st_size,
        "db_sha256": sha256_file(DB_PATH),
        "integrity_check": integrity,
        "task_count": len(task_rows),
        "event_log_count": event_count,
        "business_logical_sha256": logical_hash,
        "tasks": task_rows,
    }


def parse_staff_summary(snapshot):
    match = re.search(
        r"총\s*(\d+)\s*건\s*,?\s*페이지\s*(\d+)\s*/\s*(\d+)",
        one_line(snapshot.parser.text),
    )
    if not match:
        raise CollectionError("직원안내의 총건수·현재 페이지·전체 페이지를 찾지 못했습니다.")
    return tuple(int(value) for value in match.groups())


def parse_staff_rows(snapshot):
    parsed = []
    row_number = 0
    for cells in snapshot.parser.rows:
        if len(cells) < 4:
            continue
        first_four = [clean_text(cell) for cell in cells[:4]]
        if [one_line(cell) for cell in first_four] == ["소속", "직위", "전화번호", "업무"]:
            continue
        affiliation, position, phone, duty = first_four
        if not affiliation or "구보건소" not in affiliation:
            continue
        row_number += 1
        display = one_line(phone)
        comparison = phone_compare(display) if extract_phones(display) else ""
        parsed.append({
            "affiliation": one_line(affiliation),
            "position": one_line(position),
            "phone_display": display,
            "phone_compare": comparison,
            "duty_text_verbatim": duty,
            "page_number": snapshot.page_number,
            "row_number_on_page": row_number,
            "source_url": snapshot.final_url,
            "source_page_title": snapshot.page_title,
            "source_html_sha256": snapshot.html_sha256,
            "retrieved_at_kst": snapshot.retrieved_at_kst,
        })
    return parsed


def discover_service_urls(index_snapshot):
    urls = set()
    for href in index_snapshot.parser.links:
        candidate = urljoin(index_snapshot.final_url, html.unescape(href).strip())
        parsed = urlsplit(candidate)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
            continue
        if not parsed.path.startswith(SERVICE_PREFIXES):
            continue
        if not parsed.path.endswith((".jsp", ".do")):
            continue
        urls.add(canonical_url(candidate))
    return sorted(urls)


def context_blocks(parser):
    contexts = []
    for cells in parser.rows:
        value = " | ".join(clean_text(cell) for cell in cells if clean_text(cell))
        if value and extract_phones(value):
            contexts.append(value)
    for index, line in enumerate(parser.lines):
        if not extract_phones(line):
            continue
        start = max(0, index - 1)
        end = min(len(parser.lines), index + 2)
        contexts.append(" | ".join(parser.lines[start:end]))
    return contexts


def extract_service_contacts(snapshot):
    contacts = []
    seen = set()
    headings = [item["text"] for item in snapshot.parser.headings]
    for context in context_blocks(snapshot.parser):
        context_clean = clean_text(context)
        context_one_line = one_line(context_clean)
        affiliation_markers = list(HEALTH_AFFILIATION_RE.finditer(context_one_line))
        for occurrence in phone_occurrences(context_one_line):
            display = occurrence["display"]
            comparison = occurrence["comparison"]
            phone_start = occurrence["start"]
            phone_end = occurrence["end"]
            before = [marker for marker in affiliation_markers if marker.start() <= phone_start]
            after = [marker for marker in affiliation_markers if marker.start() > phone_end]
            nearest = before[-1] if before else after[0] if after else None
            if nearest is not None:
                distance = (
                    phone_start - nearest.end()
                    if nearest.start() <= phone_start
                    else nearest.start() - phone_end
                )
                if distance > 140:
                    nearest = None
            associated_affiliation = nearest.group(0) if nearest is not None else ""
            segment_start = context_one_line.rfind("|", 0, phone_start) + 1
            segment_end = context_one_line.find("|", phone_end)
            if segment_end < 0:
                segment_end = len(context_one_line)
            local_segment = context_one_line[segment_start:segment_end].strip()
            relative_start = max(0, phone_start - segment_start)
            role_prefix = local_segment[:relative_start]
            role_markers = list(re.finditer(r"(?i)FAX|TEL|팩스|전화|문의|☎", role_prefix))
            is_fax = bool(
                role_markers
                and re.fullmatch(r"(?i)FAX|팩스", role_markers[-1].group(0))
            )
            if is_fax:
                continue
            key = (comparison, snapshot.final_url, normalize(local_segment))
            if key in seen:
                continue
            seen.add(key)
            local_external_organization = bool(EXTERNAL_ORGANIZATION_RE.search(local_segment))
            local_public_organization = bool(EXTERNAL_PUBLIC_ORGANIZATION_RE.search(local_segment))
            local_current_affiliation = CURRENT_AFFILIATION in local_segment
            is_general = comparison in GENERAL_FALLBACK_NUMBERS
            associated_current = CURRENT_AFFILIATION in associated_affiliation
            current = associated_current and not (
                local_external_organization and not local_current_affiliation
            )
            historical_only = HISTORICAL_AFFILIATION in associated_affiliation and not current
            other_health_center = (
                bool(associated_affiliation)
                and not associated_current
                and not historical_only
            )
            explicit_inquiry = any(marker in context_one_line for marker in INQUIRY_MARKERS)
            if is_general:
                contact_type = "general_fallback"
            elif current:
                contact_type = "service_contact"
            elif local_public_organization:
                contact_type = "external_official"
            elif other_health_center or historical_only:
                contact_type = "general_fallback"
            else:
                contact_type = "general_fallback"
            contacts.append({
                "phone_display": display,
                "phone_compare": comparison,
                "contact_type": contact_type,
                "official_affiliation": (
                    CURRENT_AFFILIATION
                    if current
                    else "공식 서비스 페이지가 안내한 외부 공공기관"
                    if contact_type == "external_official"
                    else ""
                ),
                "service_context_verbatim": context_clean,
                "contact_role_verbatim": local_segment,
                "source_url": snapshot.final_url,
                "source_page_title": snapshot.page_title,
                "source_headings": headings,
                "source_html_sha256": snapshot.html_sha256,
                "retrieved_at_kst": snapshot.retrieved_at_kst,
                "historical_affiliation_only": historical_only,
                "associated_affiliation_verbatim": associated_affiliation,
                "other_health_center": other_health_center,
                "explicit_inquiry_context": explicit_inquiry,
                "eligible_for_matching": (
                    not is_general
                    and not historical_only
                    and not other_health_center
                    and (current or local_public_organization)
                ),
            })
    return contacts


def matching_aliases(task):
    for alias in task.get("aliases", []):
        try:
            weight = int(alias.get("weight") or 0)
        except (TypeError, ValueError):
            weight = 0
        if alias.get("type") == "장소어" or weight < 8:
            continue
        yield alias


def task_phrases(task):
    values = [task.get("name", ""), task.get("representative", "")]
    values.extend(alias.get("text", "") for alias in matching_aliases(task))
    context_keys = {
        normalize(task.get(field, ""))
        for field in ("department", "team", "floor", "place")
        if normalize(task.get(field, ""))
    }
    phrases = []
    seen = set()
    for value in values:
        cleaned = one_line(value)
        key = normalize(cleaned)
        if len(key) < 3 or key in GENERIC_KEYS or key in context_keys or key in seen:
            continue
        seen.add(key)
        phrases.append((cleaned, key))
    return phrases


def task_tokens(task):
    values = [task.get("name", ""), task.get("representative", "")]
    values.extend(alias.get("text", "") for alias in matching_aliases(task))
    context_tokens = {
        normalize(token)
        for field in ("department", "team", "floor", "place")
        for token in TOKEN_RE.findall(unicodedata.normalize("NFKC", str(task.get(field, ""))).lower())
        if normalize(token)
    }
    result = []
    seen = set()
    for value in values:
        for token in TOKEN_RE.findall(unicodedata.normalize("NFKC", str(value or "")).lower()):
            key = normalize(token)
            if len(key) < 2 or key in GENERIC_KEYS or key in context_tokens or key in seen:
                continue
            seen.add(key)
            result.append((token, key))
    return result


def evidence_match(task, evidence):
    evidence_norm = normalize(evidence)
    exact = [original for original, key in task_phrases(task) if key in evidence_norm]
    tokens = [original for original, key in task_tokens(task) if key in evidence_norm]
    strong_token = any(len(normalize(value)) >= 5 for value in tokens)
    if exact:
        return "exact", exact
    if len(tokens) >= 2 or strong_token:
        return "exploratory", tokens
    return "", []


def staff_candidate(task, row):
    if not row["phone_compare"]:
        return None
    if CURRENT_AFFILIATION not in row["affiliation"]:
        return None
    department = one_line(task.get("department"))
    if department and department not in row["affiliation"]:
        return None
    strength, keys = evidence_match(task, row["duty_text_verbatim"])
    if not strength:
        return None
    manager = any(marker in row["position"] or marker in row["duty_text_verbatim"] for marker in MANAGER_MARKERS)
    shared = any(marker in row["duty_text_verbatim"] for marker in ("공용번호", "팀 공용", "대표번호"))
    contact_type = "manager" if manager else "team_shared" if shared else "direct_staff"
    return {
        "phone_display": row["phone_display"],
        "phone_compare": row["phone_compare"],
        "contact_type": contact_type,
        "official_affiliation": row["affiliation"],
        "official_position": row["position"],
        "duty_text_verbatim": row["duty_text_verbatim"],
        "service_context_verbatim": "",
        "source_url": row["source_url"],
        "source_page_title": row["source_page_title"],
        "source_page_or_row": f"페이지 {row['page_number']}, 행 {row['row_number_on_page']}",
        "source_html_sha256": row["source_html_sha256"],
        "retrieved_at_kst": row["retrieved_at_kst"],
        "matched_keys": keys,
        "match_strength": strength,
        "eligible": not manager and contact_type in {"direct_staff", "team_shared"},
        "candidate_reason": "직원안내 업무분장과 직접 일치" if strength == "exact" else "직원안내 업무분장의 핵심어 후보",
    }


def service_candidate(task, contact):
    # 서비스 페이지 후보는 페이지의 현행 서비스 제목으로만 업무를 연결한다.
    # 연락처 주변 문맥은 전화 역할과 기관 구분 근거이며, 다른 하위업무를
    # 부분 문자열로 끌어오는 매칭 키로 사용하지 않는다.
    evidence = contact["source_page_title"]
    strength, keys = evidence_match(task, evidence)
    if not strength:
        return None
    if not contact["eligible_for_matching"]:
        return None
    return {
        "phone_display": contact["phone_display"],
        "phone_compare": contact["phone_compare"],
        "contact_type": contact["contact_type"],
        "official_affiliation": contact["official_affiliation"],
        "official_position": "",
        "duty_text_verbatim": "",
        "service_context_verbatim": contact["service_context_verbatim"],
        "source_url": contact["source_url"],
        "source_page_title": contact["source_page_title"],
        "source_page_or_row": "서비스 페이지 문의 문맥",
        "source_html_sha256": contact["source_html_sha256"],
        "retrieved_at_kst": contact["retrieved_at_kst"],
        "matched_keys": keys,
        "match_strength": strength,
        "eligible": contact["contact_type"] == "service_contact",
        "candidate_reason": "서비스 페이지 명칭·문의 문맥과 직접 일치" if strength == "exact" else "서비스 페이지의 핵심어 후보",
    }


def dedupe_candidates(candidates):
    result = []
    seen = set()
    for candidate in candidates:
        key = (
            candidate["phone_compare"],
            candidate["contact_type"],
            candidate["source_url"],
            candidate["source_page_or_row"],
            normalize(candidate["duty_text_verbatim"] or candidate["service_context_verbatim"]),
        )
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def candidate_sort_key(candidate):
    type_order = {
        "service_contact": 0,
        "direct_staff": 1,
        "team_shared": 2,
        "external_official": 3,
        "manager": 9,
        "general_fallback": 10,
    }
    return (
        0 if candidate["match_strength"] == "exact" else 1,
        type_order.get(candidate["contact_type"], 8),
        candidate["phone_compare"],
        candidate["source_url"],
    )


def compact_candidate(candidate):
    return {
        "phone": candidate["phone_display"],
        "comparison_phone": candidate["phone_compare"],
        "contact_type": candidate["contact_type"],
        "affiliation": candidate["official_affiliation"],
        "position": candidate["official_position"],
        "source_url": candidate["source_url"],
        "source_page_or_row": candidate["source_page_or_row"],
        "matched_keys": candidate["matched_keys"],
        "match_strength": candidate["match_strength"],
        "eligible": candidate["eligible"],
    }


def make_match(task, staff_rows, service_contacts):
    candidates = []
    for row in staff_rows:
        candidate = staff_candidate(task, row)
        if candidate:
            candidates.append(candidate)
    for contact in service_contacts:
        candidate = service_candidate(task, contact)
        if candidate:
            candidates.append(candidate)
    candidates = sorted(dedupe_candidates(candidates), key=candidate_sort_key)
    eligible = [candidate for candidate in candidates if candidate["eligible"]]
    phone_groups = defaultdict(list)
    for candidate in eligible:
        phone_groups[candidate["phone_compare"]].append(candidate)

    previous = phone_compare(task.get("phone"))
    exact_service = {
        candidate["phone_compare"] for candidate in eligible
        if candidate["match_strength"] == "exact" and candidate["contact_type"] == "service_contact"
    }
    exact_staff = {
        candidate["phone_compare"] for candidate in eligible
        if candidate["match_strength"] == "exact" and candidate["contact_type"] in {"direct_staff", "team_shared"}
    }
    conflict_note = ""
    if previous and any(phone != previous for phone in phone_groups):
        status = "conflict"
        conflict_note = "기존 DB 전화번호와 공식 후보가 다릅니다."
    elif exact_service and exact_staff and exact_service != exact_staff:
        status = "conflict"
        conflict_note = "개별 서비스 페이지와 직원안내의 직접 일치 번호가 다릅니다."
    elif len(phone_groups) > 1:
        status = "ambiguous"
    elif len(phone_groups) == 1:
        only_candidates = next(iter(phone_groups.values()))
        status = "confirmed" if any(item["match_strength"] == "exact" for item in only_candidates) else "probable_review"
    else:
        status = "unmatched"

    selected = eligible[0] if eligible else candidates[0] if candidates else None
    displays = []
    for phone in sorted(phone_groups):
        display = next(item["phone_display"] for item in phone_groups[phone])
        displays.append(display)
    candidate_phone = " | ".join(displays)
    if status == "confirmed":
        reason = "동탄구보건소 공식 원문에서 동일 역할의 유효한 직접 일치 번호가 하나 확인되었습니다."
    elif status == "probable_review":
        reason = "공식 후보 번호는 하나이나 원문 업무명이 정확히 일치하지 않아 수동 검토가 필요합니다."
    elif status == "ambiguous":
        reason = "같은 수준의 유효 후보 번호가 둘 이상이어서 자동 선택하지 않았습니다."
    elif status == "conflict":
        reason = conflict_note
    elif candidates:
        reason = "총괄자 등 자동 확정이 금지된 후보만 있어 공식 연락처 확인 필요로 유지합니다."
    else:
        reason = "동탄구보건소 공식 원문에서 이 업무에 직접 연결할 공개 번호를 찾지 못했습니다."

    row = {
        "task_id": task.get("id", ""),
        "task_name": task.get("name", ""),
        "current_department": task.get("department", ""),
        "current_team": task.get("team", ""),
        "current_floor": task.get("floor", ""),
        "current_place": task.get("place", ""),
        "previous_phone": task.get("phone", "") or "",
        "candidate_phone": candidate_phone,
        "contact_type": selected["contact_type"] if selected else "",
        "official_affiliation": selected["official_affiliation"] if selected else "",
        "official_position": selected["official_position"] if selected else "",
        "duty_text_verbatim": selected["duty_text_verbatim"] if selected else "",
        "service_context_verbatim": selected["service_context_verbatim"] if selected else "",
        "source_url": selected["source_url"] if selected else "",
        "source_page_title": selected["source_page_title"] if selected else "",
        "source_page_or_row": selected["source_page_or_row"] if selected else "",
        "source_html_sha256": selected["source_html_sha256"] if selected else "",
        "retrieved_at_kst": selected["retrieved_at_kst"] if selected else "",
        "matched_keys": " | ".join(selected["matched_keys"]) if selected else "",
        "match_status": status,
        "match_reason": reason,
        "alternative_candidates": json.dumps(
            [compact_candidate(candidate) for candidate in candidates],
            ensure_ascii=False,
        ),
        "conflict_note": conflict_note,
        "proposed_action": (
            "수동 승인 후 반영 검토" if status == "confirmed"
            else "공식 원문 수동 검토" if status in {"probable_review", "ambiguous", "conflict"}
            else "공식 연락처 확인 필요"
        ),
        "approved": "",
        "reviewer_note": "",
        "candidates": candidates,
    }
    return row


def write_csv(path, matches):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(matches)


def render_markdown(run_info, staff_data, matches, manifest, validations):
    counts = Counter(item["match_status"] for item in matches)
    lines = [
        "# 동탄구보건소 업무별 공식 연락처 후보 검토보고서",
        "",
        f"- 실행시각(KST): {run_info['started_at_kst']}",
        f"- 검색업무: {len(matches)}건",
        f"- 직원안내: 표시 {staff_data['displayed_total']}건 / 파싱 {staff_data['parsed_total']}건 / {staff_data['page_count']}페이지",
        "- 운영 반영: 수행하지 않음",
        "",
        "## 상태 요약",
        "",
    ]
    for status in ("confirmed", "probable_review", "ambiguous", "unmatched", "conflict"):
        lines.append(f"- {status}: {counts.get(status, 0)}건")
    lines.extend(["", "## 상태별 업무", ""])
    for status in ("confirmed", "probable_review", "ambiguous", "unmatched", "conflict"):
        lines.extend([f"### {status}", "", "| task_id | 업무명 | 후보번호 | 판정 이유 |", "|---|---|---|---|"])
        rows = [item for item in matches if item["match_status"] == status]
        if not rows:
            lines.append("| - | 없음 | - | - |")
        for item in rows:
            reason = one_line(item["match_reason"]).replace("|", "\\|")
            name = one_line(item["task_name"]).replace("|", "\\|")
            phone = item["candidate_phone"].replace("|", "\\|") or "공식 연락처 확인 필요"
            lines.append(f"| {item['task_id']} | {name} | {phone} | {reason} |")
        lines.append("")
    lines.extend(["## 방문한 공식 URL", ""])
    for record in manifest:
        status = record["http_status"] or "실패"
        url = record["final_url"] or record["requested_url"]
        lines.append(f"- [{status}] {url}")
    lines.extend(["", "## 자동검증", ""])
    for name, result in validations.items():
        lines.append(f"- {'PASS' if result else 'FAIL'}: {name}")
    lines.extend([
        "",
        "## 검토 주의사항",
        "",
        "- 층별시설 안내는 위치 확인에만 사용했고 전화번호 근거로 사용하지 않았습니다.",
        "- 대표 콜센터와 과장·팀장·소장 총괄번호는 일반 업무에 확정하지 않았습니다.",
        "- `approved`와 `reviewer_note`는 검토자를 위해 비워 두었습니다.",
        "- 이 보고서는 dry-run이며 운영 DB와 업무 JSON에 반영하지 않았습니다.",
        "",
    ])
    return "\n".join(lines)


def verify_outputs(output_dir, matches, manifest, source_text_by_hash, expected_task_count):
    validations = {}
    ids = [item["task_id"] for item in matches]
    validations["모든 검색업무가 검토표에 정확히 한 번 존재"] = (
        len(ids) == expected_task_count and len(set(ids)) == len(ids)
    )
    validations["중복 task_id 0건"] = len(ids) == len(set(ids))
    validations["상태 합계가 검색업무 수와 일치"] = sum(Counter(item["match_status"] for item in matches).values()) == len(matches)
    validations["다른 구 보건소 번호를 confirmed로 확정한 건 0건"] = all(
        item["match_status"] != "confirmed" or CURRENT_AFFILIATION in item["official_affiliation"]
        or item["contact_type"] == "external_official"
        for item in matches
    )
    validations["콜센터·대표번호를 개별 담당번호로 confirmed 처리한 건 0건"] = all(
        item["match_status"] != "confirmed"
        or all(phone_compare(phone) not in GENERAL_FALLBACK_NUMBERS for phone in item["candidate_phone"].split(" | "))
        for item in matches
    )
    validations["과장·팀장·소장 총괄번호를 일반 업무에 confirmed 처리한 건 0건"] = all(
        item["match_status"] != "confirmed" or item["contact_type"] != "manager"
        for item in matches
    )
    confirmed_sources_exist = True
    for item in matches:
        if item["match_status"] != "confirmed":
            continue
        source_text = source_text_by_hash.get(item["source_html_sha256"], "")
        if not source_text or item["candidate_phone"] not in source_text:
            confirmed_sources_exist = False
            break
        if not item["source_url"] or not item["retrieved_at_kst"] or not item["official_affiliation"]:
            confirmed_sources_exist = False
            break
    validations["confirmed 번호·소속·URL·확인시각이 저장한 공식 HTML에 존재"] = confirmed_sources_exist
    validations["공식 출처 URL이 모두 hscity.go.kr HTTPS"] = all(
        (urlsplit(record["final_url"] or record["requested_url"]).scheme == "https"
         and (urlsplit(record["final_url"] or record["requested_url"]).hostname or "").lower() in ALLOWED_HOSTS)
        for record in manifest
    )

    csv_path = output_dir / "contact_match_dry_run.csv"
    json_path = output_dir / "contact_match_dry_run.json"
    csv.field_size_limit(max(csv.field_size_limit(), 10 * 1024 * 1024))
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    json_rows = json.loads(json_path.read_text(encoding="utf-8"))["matches"]
    csv_projection = [(row["task_id"], row["candidate_phone"], row["match_status"]) for row in csv_rows]
    json_projection = [(row["task_id"], row["candidate_phone"], row["match_status"]) for row in json_rows]
    validations["CSV와 JSON의 전화번호·상태가 일치"] = csv_projection == json_projection
    validations["CSV가 UTF-8 BOM 형식"] = csv_path.read_bytes().startswith(b"\xef\xbb\xbf")
    return validations


def main():
    parser = argparse.ArgumentParser(description="동탄구보건소 공식 연락처 후보 dry-run 보고서를 생성합니다.")
    parser.add_argument("--check", action="store_true", help="운영 DB를 수정하지 않는 검증 전용 실행")
    parser.add_argument("--delay", type=float, default=0.25, help="공식 페이지 요청 사이 최소 간격(초)")
    parser.add_argument("--timeout", type=float, default=25.0, help="요청 제한시간(초)")
    parser.add_argument("--retries", type=int, default=2, help="제한된 재시도 횟수")
    args = parser.parse_args()
    if not args.check:
        raise SystemExit("안전을 위해 --check 옵션이 필요합니다. 이 스크립트는 운영 DB를 갱신하지 않습니다.")

    stamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    output_dir = REPORT_ROOT / stamp
    output_dir.mkdir(parents=True, exist_ok=False)
    log_path = output_dir / "build_contact_matches.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger("contact-matching")
    run_info = {"started_at_kst": now_kst(), "mode": "check", "output_dir": str(output_dir)}
    logger.info("공식 연락처 dry-run 시작: %s", output_dir)

    db_before = database_snapshot()
    tasks_json_before = sha256_file(TASKS_JSON_PATH)
    tasks = db_before.pop("tasks")
    if len(tasks) != 63:
        logger.warning("현재 업무 수가 기준 63건과 다릅니다: %s", len(tasks))

    fetcher = OfficialFetcher(output_dir, args.delay, args.timeout, args.retries, logger)
    index_snapshot = fetcher.fetch(INDEX_URL, "health_index")
    floor_snapshot = fetcher.fetch(FLOOR_URL, "floor_facilities")
    staff_first = fetcher.fetch(STAFF_URL, "staff_directory", page_number=1)
    displayed_total, current_page, page_count = parse_staff_summary(staff_first)
    if current_page != 1:
        raise CollectionError(f"직원안내 첫 요청이 1페이지가 아닙니다: {current_page}")

    staff_snapshots = [staff_first]
    staff_rows = parse_staff_rows(staff_first)
    staff_page_counts = [len(staff_rows)]
    for page_number in range(2, page_count + 1):
        query = urlencode({"q_healthNm": "dongtan", "q_currPage": page_number})
        snapshot = fetcher.fetch(
            f"{BASE_URL}/health/organ/BD_selectHealthOrganList.do?{query}",
            "staff_directory",
            page_number=page_number,
        )
        page_total, reported_page, reported_count = parse_staff_summary(snapshot)
        if page_total != displayed_total or reported_count != page_count or reported_page != page_number:
            raise CollectionError(f"직원안내 {page_number}페이지의 페이지 정보가 일치하지 않습니다.")
        parsed_rows = parse_staff_rows(snapshot)
        staff_page_counts.append(len(parsed_rows))
        staff_rows.extend(parsed_rows)
        staff_snapshots.append(snapshot)

    staff_keys = [
        (row["affiliation"], row["position"], row["phone_display"], row["duty_text_verbatim"])
        for row in staff_rows
    ]
    duplicate_staff_rows = [list(key) for key, count in Counter(staff_keys).items() if count > 1]
    staff_data = {
        "source_url": STAFF_URL,
        "displayed_total": displayed_total,
        "page_count": page_count,
        "page_row_counts": staff_page_counts,
        "parsed_total": len(staff_rows),
        "duplicate_row_count": len(duplicate_staff_rows),
        "duplicate_rows": duplicate_staff_rows,
        "rows": staff_rows,
    }
    json_dump(output_dir / "staff_directory.json", staff_data)

    service_urls = discover_service_urls(index_snapshot)
    service_pages = []
    service_contacts = []
    failed_service_urls = []
    for url in service_urls:
        try:
            snapshot = fetcher.fetch(url, "service_page")
        except CollectionError as exc:
            logger.error("서비스 페이지 수집 실패: %s", exc)
            failed_service_urls.append(url)
            continue
        contacts = extract_service_contacts(snapshot)
        service_pages.append({
            "url": snapshot.final_url,
            "page_title": snapshot.page_title,
            "html_sha256": snapshot.html_sha256,
            "retrieved_at_kst": snapshot.retrieved_at_kst,
            "contact_count": len(contacts),
        })
        service_contacts.extend(contacts)
    service_data = {
        "discovered_url_count": len(service_urls),
        "successful_page_count": len(service_pages),
        "failed_urls": failed_service_urls,
        "pages": service_pages,
        "contacts": service_contacts,
    }
    json_dump(output_dir / "service_contacts.json", service_data)

    matches = [make_match(task, staff_rows, service_contacts) for task in tasks]
    matches.sort(key=lambda item: item["task_id"])
    write_csv(output_dir / "contact_match_dry_run.csv", matches)
    dry_run_json = {
        "run": run_info,
        "summary": dict(Counter(item["match_status"] for item in matches)),
        "matches": matches,
    }
    json_dump(output_dir / "contact_match_dry_run.json", dry_run_json)

    source_text_by_hash = {
        snapshot.html_sha256: snapshot.text
        for snapshot in staff_snapshots + [index_snapshot, floor_snapshot]
    }
    for record in fetcher.manifest:
        if record["kind"] != "service_page" or not record["html_sha256"]:
            continue
        raw_path = output_dir / record["raw_path"]
        source_text_by_hash[record["html_sha256"]] = raw_path.read_text(encoding="utf-8", errors="replace")

    preliminary_validations = {
        "직원안내 표시 총건수와 실제 파싱 행 수 일치": displayed_total == len(staff_rows),
        "직원안내 전체 페이지 누락 0건": len(staff_snapshots) == page_count and all(count > 0 for count in staff_page_counts),
        "중복 직원안내 행 식별 완료": isinstance(duplicate_staff_rows, list),
        "서비스 페이지 수집 실패 0건": not failed_service_urls,
        "층별시설 페이지를 전화번호 근거로 사용하지 않음": all(
            item["source_url"] != floor_snapshot.final_url for item in matches if item["source_url"]
        ),
    }
    validations = {
        **preliminary_validations,
        **verify_outputs(output_dir, matches, fetcher.manifest, source_text_by_hash, len(tasks)),
    }

    db_after = database_snapshot()
    db_after.pop("tasks")
    tasks_json_after = sha256_file(TASKS_JSON_PATH)
    validations["운영 DB 파일 SHA-256 전후 동일"] = db_before["db_sha256"] == db_after["db_sha256"]
    validations["운영 업무·별칭 논리 SHA-256 전후 동일"] = (
        db_before["business_logical_sha256"] == db_after["business_logical_sha256"]
    )
    validations["업무 원본 JSON SHA-256 전후 동일"] = tasks_json_before == tasks_json_after
    validations["운영 DB integrity_check 정상"] = db_before["integrity_check"] == db_after["integrity_check"] == "ok"

    markdown_path = output_dir / "contact_match_review.md"
    markdown = render_markdown(run_info, staff_data, matches, fetcher.manifest, validations)
    markdown_path.write_text(markdown, encoding="utf-8")
    markdown_text = markdown_path.read_text(encoding="utf-8")
    validations["CSV·JSON·Markdown의 전화번호와 상태가 일치"] = all(
        markdown_text.count(f"| {item['task_id']} |") == 1
        and (
            not item["candidate_phone"]
            or item["candidate_phone"].replace("|", "\\|") in markdown_text
        )
        for item in matches
    )
    markdown_path.write_text(
        render_markdown(run_info, staff_data, matches, fetcher.manifest, validations),
        encoding="utf-8",
    )

    manifest_payload = {
        "run": run_info,
        "official_scope": sorted(ALLOWED_HOSTS),
        "source_count": len(fetcher.manifest),
        "sources": fetcher.manifest,
        "baseline": {
            "database_before": db_before,
            "database_after": db_after,
            "tasks_json_path": str(TASKS_JSON_PATH.resolve()),
            "tasks_json_sha256_before": tasks_json_before,
            "tasks_json_sha256_after": tasks_json_after,
        },
        "validations": validations,
    }
    json_dump(output_dir / "source_manifest.json", manifest_payload)
    run_info["finished_at_kst"] = now_kst()
    logger.info("상태 합계: %s", dict(Counter(item["match_status"] for item in matches)))
    logger.info("직원안내: 표시 %s / 파싱 %s / 페이지 %s", displayed_total, len(staff_rows), page_count)
    logger.info("공식 서비스 페이지: 성공 %s / 실패 %s", len(service_pages), len(failed_service_urls))
    logger.info("운영 DB 파일 해시 동일: %s", validations["운영 DB 파일 SHA-256 전후 동일"])
    logger.info("보고서: %s", output_dir)

    failed = [name for name, result in validations.items() if not result]
    if failed:
        logger.error("자동검증 실패: %s", "; ".join(failed))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
