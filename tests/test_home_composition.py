"""HOME visibility and search transitions, using actual JS without a backend."""

import json
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


class HomeMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("id"):
            self.elements[attributes["id"]] = (tag, attributes)


def home_markup(path="public/index.html"):
    parser = HomeMarkup()
    parser.feed((ROOT / path).read_text(encoding="utf-8"))
    return parser


def run_home_js(assertions, desktop_focus=False):
    source = (ROOT / "public/js/app.js").read_text(encoding="utf-8")
    helpers = source[source.index("function clearChildren("):source.index("function hideMapLocation(")]
    reset = source[source.index("function resetSearchView("):source.index("function setActiveFloor(")]
    search = source[source.index("function renderResults("):source.index("async function loadSuggestions(")]
    bindings = source[source.index("el('search-button').addEventListener"):
                      source.index("document.querySelectorAll('.quick-suggestion')")]
    focus = re.search(
        r"if \(matchMedia\('[^']+'\)\.matches\)\s*\{\s*queryInput\.focus\([^;]+;\s*\}",
        source,
    )
    assert focus, "Initial focus must be conditional and must preserve the HOME scroll position"
    markup = home_markup()
    program = r"""
const assert = require('node:assert/strict');
globalThis.fetch = () => { throw new Error('External network access is forbidden'); };
const calls = {requests: [], focus: [], scroll: [], media: [], resetMap: 0};
class Element {
  constructor(tag, attributes = {}) {
    this.tagName = tag.toUpperCase(); this.attributes = attributes;
    this.hidden = Object.hasOwn(attributes, 'hidden');
    this.value = ''; this.textContent = ''; this.children = []; this.dataset = {};
    this.listeners = {}; this.className = ''; this.open = false;
    this.classList = {add() {}, remove() {}, contains() { return false; }};
  }
  get firstChild() { return this.children[0] ?? null; }
  appendChild(node) { this.children.push(node); return node; }
  removeChild(node) { this.children.splice(this.children.indexOf(node), 1); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  focus(options) { calls.focus.push(options); }
  scrollIntoView(options) { calls.scroll.push({id: this.attributes.id, options}); }
  showModal() { this.open = true; }
}
const elements = new Map(Object.entries(__MARKUP__).map(
  ([id, [tag, attributes]]) => [id, new Element(tag, attributes)]));
const el = id => elements.get(id) ?? null;
const document = {body: new Element('body'), createElement: tag => new Element(tag), querySelectorAll: () => []};
const window = {scrollTo(options) { calls.scroll.push({window: true, options}); }};
const matchMedia = query => { calls.media.push(query); return {matches: __DESKTOP_FOCUS__}; };
const queryInput = el('query'), statusEl = el('status'), resultsEl = el('results');
const resultsHeadingEl = el('results-heading'), suggestionsEl = el('suggestions');
const detailEl = el('detail'), detailDialogEl = el('detail-dialog');
const state = {selectedTask: null, searchController: null, suggestionController: null};
const resetMap = () => { calls.resetMap++; };
const showDetail = () => { throw new Error('Search must not automatically open details'); };
let responseHandler = async () => { throw new Error('Unexpected request'); };
async function getJson(url, options) {
  const request = {url, method: options.method, body: JSON.parse(options.body), signal: options.signal};
  calls.requests.push(request);
  return responseHandler(request);
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
"""
    program = program.replace("__MARKUP__", json.dumps(markup.elements))
    program = program.replace("__DESKTOP_FOCUS__", json.dumps(desktop_focus))
    program += "\n" + helpers + reset + search + bindings + focus.group(0)
    program += "\n(async () => {\n" + assertions + "\n})().catch(error => {\n"
    program += "console.error(error); process.exitCode = 1;\n});\n"
    result = subprocess.run(
        ["node", "-"], input=program, capture_output=True, text=True,
        encoding="utf-8", timeout=20, cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_home_starts_without_results_and_keeps_existing_interaction_elements():
    markup = home_markup()
    workspace = markup.elements["search-workspace"]
    assert workspace[0] == "div"
    assert "workspace" in workspace[1]["class"].split()
    assert "hidden" in workspace[1]
    for element_id in (
        "query", "search-button", "clear-button", "suggestions", "results",
        "results-heading", "status", "detail-dialog", "sms-dialog", "sms-preview", "consent",
    ):
        assert element_id in markup.elements
    assert not {"sms-content-kind", "sms-contact-option", "sms-mode-notice"} & markup.elements.keys()


def test_preserved_home_keeps_approved_background_typewriter_and_footer():
    """The historical layout remains available without constraining the new HOME."""
    path = "public/qa/home-modified-a.html"
    markup = home_markup(path)
    for element_id in ("hero-atmosphere", "background-motion-toggle", "hero-subtitle-help"):
        assert element_id in markup.elements
    html = (ROOT / path).read_text(encoding="utf-8")
    assert '/qa/layer-engine.js?revision=a-whole-sky' in html
    assert '/qa/layer-home.js?revision=a-whole-sky' in html
    assert 'class="hero-subtitle-viewport"' in html
    assert 'aria-describedby="hero-subtitle-help"' in html
    assert '<footer class="site-footer" hidden>' in html


def test_reference_composition_scales_landmarks_without_transforming_background_or_results():
    """The preserved preview continues to use the unchanged reference stylesheet."""
    html = (ROOT / "public/qa/home-modified-a.html").read_text(encoding="utf-8")
    assert '/css/style.css?' in html
    css = (ROOT / "public/css/style.css").read_text(encoding="utf-8")
    composition = css.split("/* HOME reference composition:", 1)[1]
    # Inspect the HOME section only, not later independent dialog controls.
    composition = composition.split("\n/*", 1)[0]
    assert "2048 x 874" in composition
    assert "#search-workspace[hidden]{display:none!important}" in composition
    assert "@media screen and (min-width:1000px) and (min-height:600px)" in composition
    assert "--home-unit:min(.048828125vw,.114416476svh)" in composition
    for selector in (".topbar", ".hero-intro", ".hero-title", ".search-panel"):
        rule = composition.split(selector + "{", 1)[1].split("}", 1)[0]
        assert "var(--home-unit)" in rule
    assert "transform:" not in composition
    assert "position:fixed" not in composition
    assert "position:absolute" not in composition
    assert "min-height:100svh" in css
    assert ".hero-subtitle span{visibility:visible!important}" in css
    assert "@media(max-width:520px)" in css


@pytest.mark.parametrize("desktop_focus", [False, True])
def test_initial_focus_never_scrolls_or_opens_a_touch_keyboard(desktop_focus):
    run_home_js(r"""
assert.equal(el('search-workspace').hidden, true);
assert.deepEqual(calls.media, ['(min-width: 761px) and (pointer: fine)']);
assert.equal(calls.scroll.length, 0);
assert.equal(calls.requests.length, 0);
assert.equal(calls.focus.length, __COUNT__);
if (calls.focus.length) assert.deepEqual(calls.focus[0], {preventScroll: true});
""".replace("__COUNT__", "1" if desktop_focus else "0"), desktop_focus)


def test_successful_search_reveals_results_and_scrolls_after_rendering():
    run_home_js(r"""
const pending = deferred();
responseHandler = () => pending.promise;
queryInput.value = '  health  ';
const search = runSearch();
assert.equal(el('search-workspace').hidden, false);
assert.equal(calls.requests.length, 1);
assert.equal(calls.requests[0].url, '/api/search');
assert.equal(calls.requests[0].method, 'POST');
assert.deepEqual(calls.requests[0].body, {query: 'health'});
assert.equal(calls.scroll.length, 0, 'Do not scroll before the response arrives');
pending.resolve({results: [
  {id: 'TEST-A', public_title: 'First guide'},
  {id: 'TEST-B', public_title: 'Second guide'}
], total: 2});
await search;
assert.deepEqual(resultsEl.children.map(node => node.dataset.taskId), ['TEST-A', 'TEST-B']);
assert.ok(resultsHeadingEl.textContent.includes('health'));
assert.ok(statusEl.textContent.includes('2'));
assert.equal(detailDialogEl.open, false);
assert.deepEqual(calls.scroll, [{id: 'search-workspace', options: {block: 'start', behavior: 'auto'}}]);
""")


def test_zero_results_shows_empty_message_and_preserves_query_heading():
    run_home_js(r"""
responseHandler = async () => ({results: [], total: 0});
queryInput.value = 'missing';
await runSearch();
assert.equal(el('search-workspace').hidden, false);
assert.equal(resultsEl.children.length, 1);
assert.equal(resultsEl.children[0].className, 'empty');
assert.ok(resultsEl.children[0].textContent.includes('일치하는 결과가 없습니다'));
assert.ok(resultsHeadingEl.textContent.includes('missing'));
assert.ok(statusEl.textContent.includes('0'));
assert.equal(calls.resetMap, 1);
assert.equal(calls.scroll.length, 1);
""")


def test_search_error_keeps_results_region_available_and_displays_failure():
    run_home_js(r"""
responseHandler = async () => { throw new Error('Search service unavailable'); };
queryInput.value = 'health';
await runSearch();
assert.equal(el('search-workspace').hidden, false);
assert.equal(statusEl.textContent, 'Search service unavailable');
assert.equal(resultsEl.children.length, 1);
assert.ok(resultsEl.children[0].textContent.includes('오류'));
assert.equal(calls.requests.length, 1);
assert.equal(detailDialogEl.open, false);
assert.deepEqual(calls.scroll, [{id: 'search-workspace', options: {block: 'start', behavior: 'auto'}}]);
""")


@pytest.mark.parametrize("query", ["", "x"])
def test_short_search_reveals_validation_without_sending_a_request(query):
    run_home_js("queryInput.value = " + json.dumps(query) + ";\n" + r"""
state.searchController = new AbortController();
const previous = state.searchController;
await runSearch();
assert.equal(previous.signal.aborted, true);
assert.equal(el('search-workspace').hidden, false);
assert.equal(calls.requests.length, 0);
assert.ok(statusEl.textContent.includes('두 글자'));
assert.equal(resultsEl.children.length, 1);
assert.equal(resultsEl.children[0].className, 'empty');
assert.deepEqual(calls.scroll, [{id: 'search-workspace', options: {block: 'start', behavior: 'auto'}}]);
""")


def test_clear_cancels_requests_hides_results_and_returns_to_home_without_focus_scroll():
    run_home_js(r"""
queryInput.value = 'health';
el('search-workspace').hidden = false;
state.selectedTask = {id: 'TEST-A'};
state.searchController = new AbortController();
state.suggestionController = new AbortController();
const searchController = state.searchController, suggestionController = state.suggestionController;
suggestionsEl.appendChild(new Element('button'));
resultsEl.appendChild(new Element('button'));
el('clear-button').listeners.click();
assert.equal(searchController.signal.aborted, true);
assert.equal(suggestionController.signal.aborted, true);
assert.equal(queryInput.value, '');
assert.equal(suggestionsEl.children.length, 0);
assert.equal(el('search-workspace').hidden, true);
assert.equal(state.selectedTask, null);
assert.equal(resultsEl.children.length, 1);
assert.equal(resultsEl.children[0].className, 'empty');
assert.deepEqual(calls.focus, [{preventScroll: true}]);
assert.deepEqual(calls.scroll, [{window: true, options: {top: 0, behavior: 'auto'}}]);
assert.equal(calls.requests.length, 0);
""")


@pytest.mark.parametrize("late_response", ["success", "aborted"])
def test_late_search_response_after_clear_does_not_restore_results(late_response):
    run_home_js("const lateResponse = " + json.dumps(late_response) + ";\n" + r"""
const pending = deferred();
responseHandler = () => pending.promise;
queryInput.value = 'health';
const search = runSearch();
el('clear-button').listeners.click();
const clearedStatus = statusEl.textContent;
if (lateResponse === 'success') pending.resolve({results: [{id: 'LATE', public_title: 'Old guide'}]});
else pending.reject(Object.assign(new Error('Cancelled'), {name: 'AbortError'}));
await search;
assert.equal(calls.requests[0].signal.aborted, true);
assert.equal(el('search-workspace').hidden, true);
assert.equal(statusEl.textContent, clearedStatus);
assert.equal(resultsEl.children[0].className, 'empty');
assert.deepEqual(calls.scroll, [{window: true, options: {top: 0, behavior: 'auto'}}]);
""")


def test_cancelled_search_http_error_cannot_overwrite_the_service_directory():
    run_home_js(r"""
const pending = deferred();
responseHandler = () => pending.promise;
queryInput.value = 'health';
const search = runSearch();
state.searchController.abort();
queryInput.value = '';
resultsHeadingEl.textContent = '전체 업무 안내';
statusEl.textContent = '등록된 업무 63건';
pending.reject(new Error('요청을 처리하지 못했습니다.'));
await search;
assert.equal(resultsHeadingEl.textContent, '전체 업무 안내');
assert.equal(statusEl.textContent, '등록된 업무 63건');
assert.equal(calls.resetMap, 0);
""")


def test_old_same_query_response_cannot_overwrite_a_new_search():
    run_home_js(r"""
const first = deferred();
const second = deferred();
let count = 0;
responseHandler = () => count++ === 0 ? first.promise : second.promise;
queryInput.value = 'health';
const oldSearch = runSearch();
const currentSearch = runSearch();
second.resolve({results: [{id: 'NEW', public_title: 'New guide'}]});
await currentSearch;
first.resolve({results: [{id: 'OLD', public_title: 'Old guide'}]});
await oldSearch;
assert.deepEqual(resultsEl.children.map(node => node.dataset.taskId), ['NEW']);
""")
