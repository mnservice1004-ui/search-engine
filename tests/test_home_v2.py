"""HOME v2 wiring and retained business UI; no backend, service, or browser access."""

from collections import Counter
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "public/index.html"
PRESERVED_HOME = ROOT / "public/qa/home-modified-a.html"


class HomeDocument(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.tags = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def home_document():
    return HomeDocument(HOME.read_text(encoding="utf-8"))


def test_home_v2_loads_home_assets_after_existing_business_assets():
    document = home_document()
    styles = [urlsplit(attrs["href"]).path for tag, attrs in document.tags
              if tag == "link" and attrs.get("rel") == "stylesheet"]
    scripts = [(urlsplit(attrs.get("src", "")).path, attrs)
               for tag, attrs in document.tags if tag == "script"]
    script_paths = [path for path, _attrs in scripts]
    for path in ("/css/style.css", "/css/home-v2.css"):
        assert styles.count(path) == 1
        assert (ROOT / "public" / path.lstrip("/")).is_file()
    for path in ("/js/app.js", "/js/home-v2.js"):
        assert script_paths.count(path) == 1
        assert (ROOT / "public" / path.lstrip("/")).is_file()
    assert styles.index("/css/style.css") < styles.index("/css/home-v2.css")
    assert script_paths.index("/js/app.js") < script_paths.index("/js/home-v2.js")
    assert all("defer" in attrs for _path, attrs in scripts)
    assert not {"/qa/layer-engine.js", "/qa/layer-home.js", "/js/hero-atmosphere.js"} & set(script_paths)


def test_home_v2_has_unique_ids_and_retains_accessible_search_controls():
    document = home_document()
    ids = [attrs["id"] for _tag, attrs in document.tags if "id" in attrs]
    assert not {name: count for name, count in Counter(ids).items() if count > 1}
    elements = {attrs["id"]: (tag, attrs) for tag, attrs in document.tags if "id" in attrs}
    required = {"query", "search-button", "clear-button", "suggestions", "search-workspace",
                "results", "results-heading", "status", "detail-dialog", "sms-dialog", "sms-result-dialog"}
    assert required <= elements.keys()
    query_tag, query = elements["query"]
    assert query_tag == "input" and query["type"] == "search"
    assert query["maxlength"] == "80" and query["aria-controls"] == "suggestions"
    labels = [attrs.get("for") for tag, attrs in document.tags if tag == "label"]
    assert "query" in labels or query.get("aria-label")
    assert query.get("aria-describedby")
    assert set(query["aria-describedby"].split()) <= elements.keys()
    assert elements["status"][1]["role"] == "status"
    assert elements["status"][1]["aria-live"] == "polite"
    assert elements["suggestions"][1]["aria-live"] == "polite"
    assert "hidden" in elements["search-workspace"][1]
    for name in ("search-button", "clear-button"):
        tag, attrs = elements[name]
        assert tag == "button" and attrs["type"] == "button"


@pytest.mark.parametrize("dialog_id", ["detail-dialog", "sms-dialog", "sms-result-dialog"])
def test_home_v2_preserves_existing_map_detail_and_sms_dialog_markup(dialog_id):
    pattern = re.compile(r'<dialog\b[^>]*\bid="' + re.escape(dialog_id) + r'"[^>]*>.*?</dialog>', re.S)
    current = pattern.findall(HOME.read_text(encoding="utf-8"))
    previous = pattern.findall(PRESERVED_HOME.read_text(encoding="utf-8"))
    assert len(current) == len(previous) == 1
    restored = current[0]
    if dialog_id == 'detail-dialog':
        # The explicitly approved detailed-view composition adds only a title
        # context, toolbar, a viewport wrapper, and legend/status. Remove those
        # additions and still compare EVERY original business element verbatim.
        restored = restored.replace(
            'class="detail-dialog detail-v2" aria-labelledby="detail-dialog-title" aria-describedby="detail-subtitle"',
            'class="detail-dialog" aria-labelledby="detail-dialog-title"',
        )
        restored, count = re.subn(r'<p class="detail-breadcrumb">.*?</p>',
                                  '<p>선택한 민원 안내</p>', restored, flags=re.S)
        assert count == 1
        assert restored.count('          <p id="detail-subtitle"></p>\n') == 1
        restored = restored.replace('          <p id="detail-subtitle"></p>\n', '')
        restored, count = re.subn(
            r'          <div class="detail-map-toolbar">.*?'
            r'          <div class="detail-map-viewport"[^>]*>\n', '', restored, flags=re.S,
        )
        assert count == 1
        restored, count = re.subn(
            r'          </div>\n          <div class="detail-map-footer">.*?'
            r'          <p id="detail-map-status" role="status"></p>\n', '', restored, flags=re.S,
        )
        assert count == 1
    assert restored == previous[0], 'Only the approved detailed-view additions may change; original business/SMS markup remains exact'


def test_home_v2_runtime_assets_obey_the_existing_self_only_csp():
    for tag, attrs in home_document().tags:
        assert not any(key.lower().startswith("on") for key in attrs), "Inline handlers are blocked by the existing CSP"
        assert "style" not in attrs, "HOME styles belong in the scoped external stylesheet"
        if tag == "script" or (tag == "link" and attrs.get("rel") == "stylesheet"):
            value = attrs.get("src" if tag == "script" else "href", "")
            location = urlsplit(value)
            assert location.path.startswith("/") and not location.scheme and not location.netloc


def test_home_v2_does_not_rewrite_existing_business_styles():
    content = (ROOT / "public/css/style.css").read_bytes().replace(b"\r\n", b"\n")
    assert sha256(content).hexdigest() == "97a75c90f749a243cc6d39bc4e701bb7623795ded9bdf61ac5c829e44630d766"


def test_business_script_changes_are_only_approved_guards_view_hooks_and_semantic_rows():
    content = (ROOT / "public/js/app.js").read_text(encoding="utf-8")
    reset_hook = '  window.ServiceGuidanceView?.reset();\n'
    assert content.count(reset_hook) == 2
    content = content.replace(reset_hook, '')
    reset_hook = '  window.VaccinationView?.reset();\n'
    assert content.count(reset_hook) == 2
    content = content.replace(reset_hook, '')
    unified_hook = "    const guides = window.ServiceGuidanceView?.entries(data, query, async (taskId, trigger) => {\n      const task = await getJson(`/api/tasks/${encodeURIComponent(taskId)}`);\n      if (query !== queryInput.value.trim() || !trigger.isConnected) return;\n      state.detailTrigger = trigger;\n      if (!detailDialogEl.open) detailDialogEl.showModal();\n      showDetail(task);\n    }) || [];\n    const entries = window.ServiceGuidanceView?.compose(guides, items) || items;\n    renderResults(entries);\n    window.VaccinationView?.render(data.vaccination, query);\n    statusEl.textContent = `검색 결과 ${entries.length}건 · 이용 안내 ${guides.length}건 · 업무·위치 ${entries.length - guides.length}건`;\n    if (!guides.length && !items.length && window.VaccinationView?.hasResults()) {\n      resultsEl.querySelector('.empty').textContent = '일치하는 업무·이용 안내가 없습니다. 아래 참고자료를 확인할 수 있습니다.';\n    }\n"
    assert content.count(unified_hook) == 1
    content = content.replace(unified_hook, '    renderResults(items);\n')
    guide_click = "      if (task.result_kind === 'guide') { task.open(button); return; }\n"
    assert content.count(guide_click) == 1
    content = content.replace(guide_click, '')
    guide_controls = "    button.setAttribute('aria-controls', task.result_kind === 'guide' ? 'service-guide-dialog' : 'detail-dialog');"
    assert content.count(guide_controls) == 1
    content = content.replace(guide_controls, "    button.setAttribute('aria-controls', 'detail-dialog');")
    # Undo only the reviewed 2026-09-30 multi-contact binding. Keep the original
    # whole-script protection for unrelated search, map and SMS behavior.
    pdf_deltas = [
        ("  const purpose = contact.purpose || contact.role;\n"
         "  if (purpose) container.appendChild(createText('span', '', `${purpose}: `));\n", ""),
        ("  const detailContacts = [];\n"
         "  const seenPhones = new Set();\n"
         "  for (const contact of [primaryContact, ...(Array.isArray(task.contacts) ? task.contacts : [])]) {\n"
         "    if (!contact) continue;\n"
         "    const key = String(contact.phone || contact.display_phone || '').replace(/\\D/g, '');\n"
         "    if (!key || seenPhones.has(key)) continue;\n"
         "    seenPhones.add(key);\n"
         "    detailContacts.push(contact);\n"
         "  }\n"
         "  if (detailContacts.length) {\n", "  if (primaryContact) {\n"),
        ("    for (const contact of detailContacts) {\n"
         "      if (contactValue.children.length) contactValue.appendChild(document.createElement('br'));\n"
         "      appendPrimaryContact(contactValue, contact);\n"
         "    }\n", "    appendPrimaryContact(contactValue, primaryContact);\n"),
        ("      detailEl.appendChild(createText('p', 'help', detailContacts.length\n"
         "        ? '위 문의전화에서 필요한 업무의 번호를 선택해 주세요.'\n"
         "        : '문의전화는 미등록 상태이며, 안내 내용은 문자로 받을 수 있습니다.'));\n",
         "      detailEl.appendChild(createText('p', 'help', '문의전화는 미등록 상태이며, 안내 내용은 문자로 받을 수 있습니다.'));\n"),
    ]
    for revised, previous in pdf_deltas:
        assert content.count(revised) == 1
        content = content.replace(revised, previous)
    start = content.index("async function runSearch(")
    end = content.index("async function loadSuggestions(", start)
    search = content[start:end]
    controller = "  const controller = state.searchController;\n"
    guard = "    if (controller.signal.aborted || state.searchController !== controller) return;\n"
    assert search.count(controller) == 1
    assert search.count("signal: controller.signal") == 1
    assert search.count(guard) == 2
    assert guard + "    if (query !== queryInput.value.trim()) return;" in search
    assert "  } catch (error) {\n" + guard in search
    original_search = search.replace(controller, "").replace(guard, "")
    original_search = original_search.replace("signal: controller.signal", "signal: state.searchController.signal")
    original_search = original_search.replace(
        "JSON.stringify(document.body.classList.contains('results-v2') ? {query, limit: 100} : {query})",
        "JSON.stringify({query})",
    )
    original_content = content[:start] + original_search + content[end:]
    assert original_content.count("  window.ResultsView?.reset();\n") == 1
    assert original_content.count("  window.ResultsView?.render(items);\n") == 1
    original_content = original_content.replace("  window.ResultsView?.reset();\n", "")
    original_content = original_content.replace("  window.ResultsView?.render(items);\n", "")
    detail_hook = "  window.DetailView?.render(task, {isLocationGuide, primaryContact});\n"
    assert original_content.count(detail_hook) == 1
    assert '  showMap(task);\n' + detail_hook in original_content
    original_content = original_content.replace(detail_hook, '')
    # The 2026-09-09 change explicitly separates procedure / caution / extra
    # guidance. Restore only these exact approved edits before comparing the
    # complete original script hash; map, SMS, search and all other code remain
    # protected by the same baseline rather than accepting a new blanket hash.
    repeated_policy = (
        '// These cautions repeat the availability/booking step already displayed.\n'
        '// Other location cautions retain distinct intake, reservation or access advice.\n'
        "const LOCATION_REPEATED_CAUTION_IDS = new Set(['F103', 'F201', 'F204']);\n\n"
    )
    assert 'LOCATION_REPEATED_CAUTION_IDS' not in original_content
    assert original_content.count('function isLocationOnlyGuide(task) {') == 1
    original_content = original_content.replace('function isLocationOnlyGuide(task) {',
                                                repeated_policy + 'function isLocationOnlyGuide(task) {')
    new_location = (
        'function getLocationVisitText(task) {\n'
        '  // Directions and cautions have different meanings; never merge them into\n'
        '  // an apparent sequence of actions for a visitor.\n'
        "  return task?.visit_steps || '';\n}\n"
    )
    old_location = (
        'function getLocationVisitText(task) {\n'
        '  return joinPublicText([\n'
        '    task.visit_steps,\n'
        '    LOCATION_REPEATED_CAUTION_IDS.has(task.id) ? null : task.public_caution\n'
        '  ]);\n}\n'
    )
    assert original_content.count(new_location) == 1
    original_content = original_content.replace(new_location, old_location)
    new_procedure = '    isGuidedTask ? (isLocationGuide ? getLocationVisitText(task) : task.visit_steps) : null,\n'
    old_procedure = ('    isGuidedTask ? (isLocationGuide ? getLocationVisitText(task)\n'
                     '      : joinPublicText([task.visit_steps, task.primary_action])) : null,\n')
    assert original_content.count(new_procedure) == 1
    original_content = original_content.replace(new_procedure, old_procedure)
    extra_row = (
        '  if (!isLocationGuide && task.primary_action !== task.visit_steps) {\n'
        "    addDetailRow(detailEl, '추가 안내', isGuidedTask ? task.primary_action : null);\n"
        '  }\n'
    )
    assert original_content.count(extra_row) == 1
    original_content = original_content.replace(extra_row, '')
    caution_row = "  addDetailRow(detailEl, '꼭 알아두세요', isGuidedTask ? task.public_caution : null);\n"
    assert original_content.count(caution_row) == 1
    original_content = original_content.replace(caution_row, '  if (!isLocationGuide) {\n  ' + caution_row + '  }\n')
    assert sha256(original_content.encode("utf-8")).hexdigest() == "43beb385d045b719719af10a3a88d956c0d9286d3b41a145a1e1c3722c001766"


def test_home_v2_categories_and_location_use_native_accessible_controls():
    document = home_document()
    categories = [(tag, attrs) for tag, attrs in document.tags if "data-home-category" in attrs]
    assert {attrs["data-home-category"] for _tag, attrs in categories} == {
        "certificate", "vaccination", "family", "location",
    }
    assert len(categories) == 4  # Original HOME controls; reference cards now link to their official services.
    controls = categories + [(tag, attrs) for tag, attrs in document.tags
                             if "data-home-location" in attrs or "data-home-browse" in attrs]
    assert all(tag == "button" and attrs.get("type") == "button" for tag, attrs in controls)
    elements = {attrs["id"]: (tag, attrs) for tag, attrs in document.tags if "id" in attrs}
    tag, dialog = elements["location-dialog"]
    assert tag == "dialog" and dialog["aria-labelledby"] == "location-title"
    close_tag, close = elements["close-location"]
    assert close_tag == "button" and close["type"] == "button" and close.get("aria-label")
    for tag, attrs in document.tags:
        if tag == "a" and attrs.get("target") == "_blank":
            assert {"noopener", "noreferrer"} <= set(attrs.get("rel", "").split())
