"""Exercise the compact dialog against its actual JS, with no service or DB access."""

import json
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "public" / "js" / "app.js"
INDEX_HTML = ROOT / "public" / "index.html"
REMOVED_IDS = ("sms-content-kind", "sms-contact-option", "sms-mode-notice")


class DialogMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = {}
        self.labels = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("id"):
            self.elements[attributes["id"]] = (tag, attributes)
        if tag == "label":
            self.labels.append(attributes.get("for"))


def dialog_markup():
    html = INDEX_HTML.read_text(encoding="utf-8")
    dialog = html.split('<dialog id="sms-dialog"', 1)[1].split("</dialog>", 1)[0]
    parser = DialogMarkup()
    parser.feed('<dialog id="sms-dialog"' + dialog + "</dialog>")
    return dialog, parser


def run_dialog_js(assertions):
    source = APP_JS.read_text(encoding="utf-8")
    constant = re.search(r"const SMS_MESSAGE_KIND\s*=\s*[^;]+;", source)
    assert constant, "The dialog must use one fixed message kind"
    functions_start = min(source.index("let smsPreviewVersion ="), constant.start())
    functions_end = source.index("el('search-button').addEventListener", functions_start)
    functions = source[functions_start:functions_end]
    bindings = source.split("el('sms-form').addEventListener", 1)[1].split(
        "el('close-detail').addEventListener", 1
    )[0]
    markup = DialogMarkup()
    markup.feed(INDEX_HTML.read_text(encoding="utf-8"))
    program = r"""
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
globalThis.fetch = () => { throw new Error('Network access is forbidden in this test'); };
const ids = __DIALOG_IDS__;
const elements = new Map(ids.map(id => [id, {
  id, isConnected: true,
  value: '', textContent: '', checked: false, disabled: false, readOnly: false,
  open: false, listeners: {},
  addEventListener(name, callback) { this.listeners[name] = callback; },
  focus(options) { document.activeElement = this; this.lastFocusOptions = options; },
  showModal() { this.open = true; transitions.push('open:' + this.id); this.focus(); },
  close() {
    if (!this.open) return;
    this.open = false;
    transitions.push('close:' + this.id);
    this.listeners.close?.({target: this});
  }
}]));
const transitions = [];
const smsTrigger = {isConnected: true, focusCount: 0,
  focus(options) { document.activeElement = this; this.focusCount++; this.lastFocusOptions = options; }};
const document = {activeElement: smsTrigger, getElementById: id => elements.get(id) ?? null};
// Missing elements behave like real getElementById, exposing stale DOM references.
const el = id => elements.get(id) ?? null;
const state = {selectedTask: {id: 'TEST-GUIDE', public_title: 'Test guide'}};
const requests = [];
let responseHandler = async () => { throw new Error('Unexpected request'); };
async function getJson(url, options) {
  const request = {url, method: options.method, body: JSON.parse(options.body)};
  requests.push(request);
  return responseHandler(request);
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
const event = {prevented: 0, preventDefault() { this.prevented++; }};
const flush = () => new Promise(resolve => setImmediate(resolve));
function dispatchEscape(dialog) {
  const cancelEvent = {target: dialog, prevented: false,
    preventDefault() { this.prevented = true; }};
  dialog.listeners.cancel?.(cancelEvent);
  if (!cancelEvent.prevented) dialog.close();
  return cancelEvent;
}
async function openReadyDialog() {
  responseHandler = async request => {
    assert.equal(request.url, '/api/sms/preview');
    return {text: 'Guide', ready: true, notice: ''};
  };
  document.activeElement = smsTrigger;
  openSmsDialog({currentTarget: smsTrigger});
  await flush();
  el('recipient').value = '01000000000';
  el('consent').checked = true;
}
""".replace("__DIALOG_IDS__", json.dumps(list(markup.elements)))
    program += "\n" + functions
    program += "\nel('sms-form').addEventListener" + bindings
    program += "\n(async () => {\n" + assertions + "\n})().catch(error => {\n"
    program += "console.error(error); process.exitCode = 1;\n});\n"
    result = subprocess.run(
        ["node", "-"],
        input=program,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_compact_markup_removes_requested_sections_and_keeps_send_controls():
    dialog, markup = dialog_markup()
    for element_id in REMOVED_IDS:
        assert element_id not in markup.elements
    assert "sms-content-kind" not in markup.labels
    assert "<select" not in dialog
    assert "수신번호를 DB와 분석 로그에 저장하지 않습니다" not in dialog
    assert "발송 서비스의 처리·보관 정책" not in dialog
    required = {
        "sms-form": "form", "sms-title": "h2", "sms-task-name": "p",
        "sms-preview": "textarea", "recipient": "input", "consent": "input",
        "sms-status": "p", "cancel-sms": "button", "send-sms": "button",
    }
    for element_id, tag in required.items():
        assert markup.elements[element_id][0] == tag
    assert '<h2 id="sms-title">안내내용 문자로 받기</h2>' in dialog
    assert "readonly" in markup.elements["sms-preview"][1]
    assert "required" in markup.elements["recipient"][1]
    assert markup.elements["consent"][1]["type"] == "checkbox"
    assert "required" in markup.elements["consent"][1]
    assert re.search(r'<label\s+for="sms-preview">안내내용</label>', dialog)
    assert re.search(r'<label\s+for="recipient">수신자 번호</label>', dialog)
    consent = re.search(r'<label class="consent-row">(.*?)</label>', dialog, re.S)
    assert consent
    consent_text = re.sub(r"<[^>]+>", "", consent.group(1)).strip()
    assert consent_text == "문자 발송을 위해 번호와 내용을 발송 서비스에 제공하는 것에 동의합니다."
    assert markup.elements["sms-status"][1]["aria-live"] == "polite"
    assert markup.elements["cancel-sms"][1]["type"] == "button"
    assert markup.elements["send-sms"][1]["type"] == "submit"
    source = APP_JS.read_text(encoding="utf-8")
    assert all(element_id not in source for element_id in REMOVED_IDS)


def test_preview_uses_guidance_and_blocks_send_until_ready_without_normal_notice():
    run_dialog_js(r"""
const pending = deferred();
responseHandler = () => pending.promise;
const preview = updateSmsPreview();
assert.equal(requests.length, 1);
assert.equal(requests[0].url, '/api/sms/preview');
assert.deepEqual(requests[0].body, {task_id: 'TEST-GUIDE', message_kind: 'guidance'});
assert.equal(smsPreviewReady, false);
assert.equal(el('send-sms').disabled, true);
assert.equal(el('sms-preview').value, '');
assert.ok(el('sms-status').textContent.length > 0);
await submitSms(event);
assert.equal(event.prevented, 1);
assert.equal(requests.length, 1, 'A pending preview must not permit sending');
pending.resolve({text: 'Guide and registered contact', ready: true, mode: 'live',
  notice: 'Normal provider mode notice must not occupy the compact dialog'});
await preview;
assert.equal(el('sms-preview').value, 'Guide and registered contact');
assert.equal(smsPreviewReady, true);
assert.equal(el('send-sms').disabled, false);
assert.equal(el('sms-status').textContent, '');
""")


@pytest.mark.parametrize("scenario", ["preview_error", "not_ready"])
def test_preview_failure_or_unavailable_service_remains_visible_and_blocks_send(scenario):
    run_dialog_js("const scenario = " + json.dumps(scenario) + ";\n" + r"""
const expected = scenario === 'preview_error' ? 'Preview could not be loaded' : 'SMS unavailable';
responseHandler = async () => {
  if (scenario === 'preview_error') throw new Error(expected);
  return {text: 'Guide', ready: false, mode: 'live', notice: expected};
};
await updateSmsPreview();
assert.equal(el('sms-status').textContent, expected);
assert.equal(smsPreviewReady, false);
assert.equal(el('send-sms').disabled, true);
await submitSms(event);
assert.equal(requests.length, 1);
assert.equal(requests[0].url, '/api/sms/preview');
""")


def test_stale_preview_cannot_replace_latest_dialog_content_or_status():
    run_dialog_js(r"""
const older = deferred(), latest = deferred();
responseHandler = () => requests.length === 1 ? older.promise : latest.promise;
const first = updateSmsPreview(), second = updateSmsPreview();
latest.resolve({text: 'Latest guide', ready: true, notice: 'Normal notice'});
await second;
older.resolve({text: 'Outdated guide', ready: false, notice: 'Outdated failure'});
await first;
assert.equal(el('sms-preview').value, 'Latest guide');
assert.equal(el('sms-status').textContent, '');
assert.equal(smsPreviewReady, true);
assert.equal(el('send-sms').disabled, false);
""")


def test_opening_dialog_clears_previous_recipient_consent_and_request():
    run_dialog_js(r"""
responseHandler = async () => ({text: 'Guide', ready: true, notice: 'Normal notice'});
el('recipient').value = '01000000000';
el('consent').checked = true;
el('sms-status').textContent = 'Earlier submission result';
smsRequestId = 'previous-request';
openSmsDialog();
assert.equal(el('recipient').value, '');
assert.equal(el('consent').checked, false);
assert.equal(el('sms-dialog').open, true);
assert.equal(el('sms-task-name').textContent, 'Test guide');
assert.notEqual(smsRequestId, 'previous-request');
await flush();
assert.equal(el('sms-status').textContent, '');
const firstRequestId = smsRequestId;
el('recipient').value = '01000000001';
el('consent').checked = true;
el('cancel-sms').listeners.click();
assert.equal(el('sms-dialog').open, false);
openSmsDialog();
await flush();
assert.equal(el('recipient').value, '');
assert.equal(el('consent').checked, false);
assert.notEqual(smsRequestId, firstRequestId);
assert.equal(requests.length, 2);
assert.ok(requests.every(request => request.body.message_kind === 'guidance'));
""")


def test_submit_preserves_guidance_consent_request_id_and_busy_protection():
    run_dialog_js(r"""
await openReadyDialog();
const pending = deferred();
responseHandler = () => pending.promise;
const previewRequestId = smsRequestId;
el('recipient').value = '01000000000';
el('consent').checked = true;
const submit = submitSms(event);
assert.equal(smsBusy, true);
assert.equal(el('send-sms').disabled, true);
assert.equal(el('recipient').readOnly, true);
assert.equal(el('consent').disabled, true);
assert.equal(el('cancel-sms').disabled, true);
el('cancel-sms').listeners.click(event);
assert.equal(el('sms-dialog').open, true, 'Cancel must not close an in-flight request');
assert.equal(dispatchEscape(el('sms-dialog')).prevented, true);
assert.equal(el('sms-dialog').open, true, 'Escape must not close an in-flight request');
assert.equal(el('sms-result-dialog').open, false);
assert.equal(requests[1].url, '/api/sms');
assert.equal(requests[1].method, 'POST');
assert.deepEqual(requests[1].body, {task_id: 'TEST-GUIDE', recipient: '01000000000',
  consent: true, message_kind: 'guidance', request_id: previewRequestId});
await submitSms(event);
assert.equal(requests.length, 2, 'A second click must not send while busy');
pending.resolve({status: 'accepted', provider: 'solapi'});
await submit;
assert.equal(smsBusy, false);
assert.equal(smsPreviewReady, false);
assert.equal(el('send-sms').disabled, true);
assert.equal(el('recipient').readOnly, false);
assert.equal(el('consent').disabled, false);
assert.equal(el('cancel-sms').disabled, false);
assert.equal(el('sms-dialog').open, false);
assert.equal(el('sms-result-dialog').open, true);
assert.equal(el('sms-result-title').textContent, '발송되었습니다');
assert.match(el('sms-result-message').textContent, /접수/);
assert.match(el('sms-result-message').textContent, /수신/);
assert.ok(transitions.indexOf('close:sms-dialog') < transitions.indexOf('open:sms-result-dialog'));
await submitSms(event);
assert.equal(requests.length, 2, 'An accepted request must not be sent again');
""")


def test_submit_failure_keeps_same_request_id_and_never_automatically_retries():
    run_dialog_js(r"""
await openReadyDialog();
responseHandler = async request => {
  if (request.url === '/api/sms/preview') return {text: 'Guide', ready: true, notice: ''};
  throw new Error('Provider result requires confirmation');
};
el('recipient').value = '01000000000';
el('consent').checked = true;
const requestId = smsRequestId;
await submitSms(event);
await flush();
assert.equal(requests.length, 2);
assert.equal(smsBusy, false);
assert.equal(el('recipient').readOnly, false);
assert.equal(el('consent').disabled, false);
assert.equal(el('cancel-sms').disabled, false);
assert.equal(el('send-sms').disabled, false);
assert.equal(el('sms-dialog').open, true);
assert.equal(el('sms-result-dialog').open, false);
assert.ok(!transitions.includes('open:sms-result-dialog'));
assert.equal(el('sms-status').textContent, 'Provider result requires confirmation');
assert.equal(smsRequestId, requestId);
await submitSms(event);
assert.equal(requests.length, 3);
assert.equal(requests[1].body.request_id, requestId);
assert.equal(requests[2].body.request_id, requestId);
""")


def test_recipient_edit_rotates_request_id_and_consent_is_not_assumed():
    run_dialog_js(r"""
responseHandler = async request => request.url === '/api/sms/preview'
  ? {text: 'Guide', ready: true, notice: ''} : {status: 'mocked'};
await updateSmsPreview();
const previousId = smsRequestId;
el('recipient').value = '01000000001';
el('recipient').listeners.input();
assert.notEqual(smsRequestId, previousId);
el('consent').checked = false;
await submitSms(event);
// Native required-checkbox validation and the server enforce consent; JS must
// preserve the actual checkbox value rather than inventing consent.
assert.equal(requests[1].body.consent, false);
assert.equal(requests[1].body.request_id, smsRequestId);
assert.equal(el('sms-form').listeners.submit, submitSms);
""")


def test_result_dialog_has_distinct_accessible_title_message_and_close_control():
    markup = DialogMarkup()
    markup.feed(INDEX_HTML.read_text(encoding="utf-8"))
    required = {
        "sms-result-dialog": "dialog", "sms-result-title": "h2",
        "sms-result-message": "p", "close-sms-result": "button",
    }
    for element_id, tag in required.items():
        assert markup.elements[element_id][0] == tag
    assert markup.elements["sms-result-dialog"][1]["aria-labelledby"] == "sms-result-title"
    assert markup.elements["close-sms-result"][1]["type"] == "button"
    source = APP_JS.read_text(encoding="utf-8")
    assert "function showSmsResult(data)" in source
    assert "function dismissSmsResult(event)" in source


def test_mocked_submit_has_explicit_non_delivery_result_instead_of_live_success():
    run_dialog_js(r"""
await openReadyDialog();
responseHandler = async () => ({status: 'mocked'});
await submitSms(event);
assert.equal(el('sms-dialog').open, false);
assert.equal(el('sms-result-dialog').open, true);
assert.match(el('sms-result-title').textContent, /^모의 발송.*완료/);
assert.match(el('sms-result-message').textContent, /실제/);
assert.match(el('sms-result-message').textContent, /발송되지 않았|전송되지 않았|발송되지 않|전송되지 않/);
assert.equal(smsBusy, false);
assert.equal(smsPreviewReady, false);
assert.equal(el('recipient').readOnly, false);
assert.equal(el('consent').disabled, false);
assert.equal(el('cancel-sms').disabled, false);
await submitSms(event);
assert.equal(requests.length, 2, 'A mocked result must also prevent repeat submission');
""")


@pytest.mark.parametrize("status", [None, "queued", "failed"])
def test_unknown_submit_status_is_an_error_and_never_opens_success_result(status):
    run_dialog_js("const returnedStatus = " + json.dumps(status) + ";\n" + r"""
await openReadyDialog();
const requestId = smsRequestId;
responseHandler = async () => returnedStatus === null ? {} : {status: returnedStatus};
await submitSms(event);
await flush();
assert.equal(requests.length, 2, 'An unknown result must not trigger an automatic retry');
assert.equal(el('sms-dialog').open, true);
assert.equal(el('sms-result-dialog').open, false);
assert.ok(!transitions.includes('close:sms-dialog'));
assert.ok(!transitions.includes('open:sms-result-dialog'));
assert.ok(el('sms-status').textContent.trim().length > 0, 'An unknown result needs visible error feedback');
assert.ok(!el('sms-status').textContent.includes('발송되었습니다'));
assert.equal(smsRequestId, requestId);
assert.equal(smsBusy, false);
assert.equal(el('recipient').readOnly, false);
assert.equal(el('consent').disabled, false);
assert.equal(el('cancel-sms').disabled, false);
""")


@pytest.mark.parametrize("dismissal", ["dialog_surface", "close_button", "escape"])
def test_result_dismissal_returns_focus_to_original_detail_sms_trigger(dismissal):
    run_dialog_js("const dismissal = " + json.dumps(dismissal) + ";\n" + r"""
await openReadyDialog();
responseHandler = async () => ({status: 'accepted'});
await submitSms(event);
const resultDialog = el('sms-result-dialog');
assert.equal(resultDialog.open, true);
el('close-sms-result').focus();
assert.notEqual(document.activeElement, smsTrigger);
if (dismissal === 'dialog_surface') {
  // A click on native dialog padding or its backdrop has the dialog as target.
  resultDialog.listeners.click({target: resultDialog});
} else if (dismissal === 'close_button') {
  el('close-sms-result').listeners.click({target: el('close-sms-result')});
} else {
  dispatchEscape(resultDialog);
}
await flush();
assert.equal(resultDialog.open, false);
assert.equal(el('sms-dialog').open, false);
assert.equal(document.activeElement, smsTrigger, 'Return focus to the original detail SMS button');
assert.ok(smsTrigger.focusCount >= 1);
assert.equal(requests.length, 2, 'Closing a result must not send or reload anything');
""")


def test_result_content_click_does_not_dismiss_the_result_dialog():
    run_dialog_js(r"""
await openReadyDialog();
responseHandler = async () => ({status: 'accepted'});
await submitSms(event);
const resultDialog = el('sms-result-dialog');
resultDialog.listeners.click({target: el('sms-result-title')});
assert.equal(resultDialog.open, true);
resultDialog.listeners.click({target: el('sms-result-message')});
assert.equal(resultDialog.open, true);
assert.equal(requests.length, 2);
""")


def test_sms_fields_have_distinct_backgrounds_and_larger_visible_consent_control():
    css = (ROOT / "public" / "css" / "style.css").read_text(encoding="utf-8")

    def declarations(selector):
        result = {}
        for block in re.findall(re.escape(selector) + r"\s*\{([^{}]*)\}", css):
            for declaration in block.split(";"):
                if ":" in declaration:
                    name, value = declaration.split(":", 1)
                    result[name.strip()] = value.strip()
        return result

    preview = declarations("#sms-preview")
    recipient = declarations("#sms-dialog #recipient")
    consent = declarations("#sms-dialog #consent")
    checked = declarations("#sms-dialog #consent:checked")
    assert preview["background"] == "#eef6f7"
    assert recipient["background"] == "#fff8e8"
    assert preview["background"] != recipient["background"]
    assert consent["width"] == consent["height"] == consent["min-width"] == "28px"
    assert checked["background"] == checked["border-color"] == "#087f8c"


@pytest.mark.parametrize(
    ("public_title", "expected_heading"),
    [
        ("예방접종 장소와 준비사항을 확인하고 싶으신가요?", "예방접종 장소와 준비사항을 알려드릴게요."),
        ("진료 접수 안내", "진료 접수 안내"),
        ("예방접종 장소와 준비사항을 확인하고 싶으신가요", "예방접종 장소와 준비사항을 확인하고 싶으신가요"),
        (" 예방접종 장소와 준비사항을 확인하고 싶으신가요?", " 예방접종 장소와 준비사항을 확인하고 싶으신가요?"),
        ("예방접종 장소와 준비사항을 확인하고 싶으신가요? ", "예방접종 장소와 준비사항을 확인하고 싶으신가요? "),
    ],
)
def test_sms_task_heading_rephrases_only_the_exact_vaccination_title(public_title, expected_heading):
    run_dialog_js(
        "const title = " + json.dumps(public_title) + ";\n"
        "const expectedHeading = " + json.dumps(expected_heading) + ";\n"
        + r"""
const task = {id: 'HEADING-FIXTURE', public_title: title};
const original = JSON.stringify(task);
assert.equal(smsTaskHeading(task), expectedHeading);
assert.equal(JSON.stringify(task), original, 'Heading formatting must not mutate task data');
assert.equal(requests.length, 0, 'Formatting the visible heading must not request anything');
"""
    )


def test_rephrased_dialog_heading_never_rewrites_preview_task_or_submission_payload():
    run_dialog_js(r"""
const publicTitle = '예방접종 장소와 준비사항을 확인하고 싶으신가요?';
const task = {id: 'VACCINE-FIXTURE', public_title: publicTitle};
state.selectedTask = task;
const originalTask = JSON.stringify(task);
const previewData = {text: publicTitle + '\n원본 안내 내용과 문의전화입니다.', ready: true, mode: 'live'};
const originalPreview = JSON.stringify(previewData);
responseHandler = async () => previewData;
openSmsDialog({currentTarget: smsTrigger});
await flush();
assert.equal(el('sms-task-name').textContent, '예방접종 장소와 준비사항을 알려드릴게요.');
assert.equal(el('sms-preview').value, previewData.text);
assert.equal(JSON.stringify(previewData), originalPreview);
assert.equal(state.selectedTask, task);
assert.equal(JSON.stringify(state.selectedTask), originalTask);
assert.deepEqual(requests[0], {url: '/api/sms/preview', method: 'POST',
  body: {task_id: 'VACCINE-FIXTURE', message_kind: 'guidance'}});
el('recipient').value = '01000000000';
el('consent').checked = true;
const requestId = smsRequestId;
responseHandler = async () => ({status: 'accepted'});
await submitSms(event);
assert.equal(requests.length, 2);
assert.deepEqual(requests[1], {url: '/api/sms', method: 'POST',
  body: {task_id: 'VACCINE-FIXTURE', recipient: '01000000000', consent: true,
    message_kind: 'guidance', request_id: requestId}});
assert.equal(state.selectedTask, task);
assert.equal(JSON.stringify(state.selectedTask), originalTask);
assert.equal(el('sms-preview').value, previewData.text);
assert.equal(JSON.stringify(previewData), originalPreview);
""")


def test_sms_heading_and_field_labels_have_thin_gray_rules_and_task_indent():
    css = (ROOT / "public" / "css" / "style.css").read_text(encoding="utf-8")
    for selector in ("#sms-title", "#sms-task-name", "#sms-form>label[for]"):
        blocks = re.findall(re.escape(selector) + r"\s*\{([^{}]*)\}", css)
        assert blocks, selector
        declarations = dict(
            (name.strip(), value.strip())
            for declaration in blocks[-1].split(";")
            if ":" in declaration
            for name, value in [declaration.split(":", 1)]
        )
        assert declarations["border-bottom"] == "1px solid #e5e7eb", selector
        if selector == "#sms-task-name":
            padding_left = declarations.get("padding-left")
            if padding_left is None:
                padding = declarations["padding"].split()
                assert 1 <= len(padding) <= 4
                padding_left = padding[{1: 0, 2: 1, 3: 1, 4: 3}[len(padding)]]
            assert padding_left == "12px"
