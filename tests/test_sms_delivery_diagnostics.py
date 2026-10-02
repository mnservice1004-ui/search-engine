"""Exercise the installed Solapi SDK with synthetic, socket-blocked transports."""

import hashlib
import hmac
import json
import logging
import re
import socket
import uuid

import httpx
import pytest
import solapi.services.message_service as sdk_messages

import sms_cloud_guard as guard
import sms_service as sms


RECIPIENT = "01000000000"
SENDER = "0212345678"
API_KEY = "synthetic-private-api-key"
API_SECRET = "synthetic-private-api-secret"
PRIVATE_TEXT = "synthetic-private-message-body"
PRIVATE_DETAIL = "synthetic-private-provider-detail"
GROUP_ID = "synthetic-private-group-id"
SENSITIVE = (RECIPIENT, SENDER, API_KEY, API_SECRET, PRIVATE_TEXT,
             PRIVATE_DETAIL, GROUP_ID, "synthetic-private-account-id")


@pytest.fixture(autouse=True)
def live_without_network(monkeypatch, caplog):
    """Never use real credentials, sockets, or process-local request history."""
    monkeypatch.delenv("VERCEL", raising=False)
    for key, value in {
        "SMS_MODE": "live", "SOLAPI_API_KEY": API_KEY,
        "SOLAPI_API_SECRET": API_SECRET, "SOLAPI_SENDER": SENDER,
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sms, "_send_requests", {})

    def blocked(*args, **kwargs):
        pytest.fail("SMS diagnostics tests must never access a real network")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    caplog.set_level(logging.DEBUG)


def _task():
    return {"public_title": "합성 안내", "public_summary": PRIVATE_TEXT,
            "route": "합성실", "primary_contact": {"phone": SENDER}}


def _response(*, registered_success=1, registered_failed=0, failed=None):
    """A complete SDK-valid send-many response, including ignored private data."""
    cash = {"requested": 0, "replacement": 0, "refund": 0, "sum": 0}
    return {
        "failedMessageList": failed or [],
        "groupInfo": {
            "count": {"total": 1, "sentTotal": 0, "sentSuccess": 0,
                      "sentPending": 0, "sentReplacement": 0, "refund": 0,
                      "registeredFailed": registered_failed,
                      "registeredSuccess": registered_success},
            "countForCharge": {}, "balance": cash, "point": cash,
            "app": {}, "log": [{"private": PRIVATE_DETAIL}], "status": "PENDING",
            "allowDuplicates": False, "isRefunded": False,
            "accountId": "synthetic-private-account-id", "masterAccountId": None,
            "apiVersion": "v4", "groupId": GROUP_ID, "price": {},
            "dateCreated": None, "dateUpdated": None,
        },
    }


def _failed_message(code):
    return {"to": RECIPIENT, "from": SENDER, "type": "LMS", "country": "82",
            "statusMessage": " ".join(SENSITIVE), "messageId": PRIVATE_DETAIL,
            "statusCode": code, "accountId": "synthetic-private-account-id",
            "customFields": {"private": PRIVATE_TEXT}}


def _transport(monkeypatch, *, response=None, error=None):
    calls = []

    def fetcher(auth_parameter, request, data=None):
        calls.append((request, data))
        assert auth_parameter == {"api_key": API_KEY, "api_secret": API_SECRET}
        assert request["url"].endswith("/messages/v4/send-many/detail")
        assert len(data["messages"]) == 1
        assert data["messages"][0]["to"] == RECIPIENT
        assert data["messages"][0]["from"] == SENDER
        if error is not None:
            raise error
        return response

    monkeypatch.setattr(sdk_messages, "default_fetcher", fetcher)
    return calls


def _assert_diagnostic(caplog, error, *, status, stage, category=None,
                       provider_code=None, extra_private=()):
    assert error.delivery_status == status
    assert re.fullmatch(r"SMS-[0-9a-f]{12}", error.diagnostic_id)
    assert error.diagnostic_id in str(error)
    assert re.search(r"[가-힣]", str(error))
    records = [record for record in caplog.records if record.name == "sms_delivery"]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.exc_info is None and record.exc_text is None and record.stack_info is None
    payload = json.loads(record.getMessage())
    assert set(payload) == {"event", "diagnostic_id", "delivery_status",
                            "category", "stage", "provider_code"}
    assert payload["event"] == "sms_delivery_failure"
    assert payload["diagnostic_id"] == error.diagnostic_id
    assert payload["delivery_status"] == status
    assert payload["stage"] == stage
    assert re.fullmatch(r"[a-z_]+", payload["category"])
    assert payload["category"] == error.category
    if category is not None:
        assert payload["category"] == category
    if provider_code is not None:
        assert payload["provider_code"] == provider_code
    exposed = caplog.text + str(error) + repr(vars(error))
    for value in (*SENSITIVE, *extra_private):
        assert value not in exposed
    assert "Traceback" not in exposed
    return payload


def test_actual_sdk_acceptance_is_cached_without_second_transport(monkeypatch, caplog):
    calls = _transport(monkeypatch, response=_response())
    request_id = str(uuid.uuid4())
    first = sms.send_contact_sms(_task(), RECIPIENT, "guidance", request_id)
    second = sms.send_contact_sms(_task(), RECIPIENT, "guidance", request_id)
    assert first == second == {"status": "accepted", "provider": "solapi",
                               "message_group_id": GROUP_ID}
    assert len(calls) == 1
    assert PRIVATE_TEXT in calls[0][1]["messages"][0]["text"]
    assert not [record for record in caplog.records if record.name == "sms_delivery"]


@pytest.mark.parametrize("code,category", [
    ("1030", "provider_balance"), ("2230", "provider_balance"),
    ("1060", "provider_sender"), ("1062", "provider_sender"),
    ("2062", "provider_sender"), ("1059", "provider_rejected"),
    ("InvalidApiKey" + PRIVATE_DETAIL, "provider_rejected"),
])
def test_actual_sdk_all_failed_registration_is_rejected(monkeypatch, caplog, code, category):
    calls = _transport(monkeypatch, response=_response(
        registered_success=0, registered_failed=1, failed=[_failed_message(code)]))
    with pytest.raises(sms.SmsDeliveryError) as caught:
        sms._send_live(RECIPIENT, PRIVATE_TEXT)
    assert len(calls) == 1
    _assert_diagnostic(caplog, caught.value, status="rejected", stage="send",
                       category=category,
                       provider_code="unclassified" if category == "provider_rejected" else code)


def test_actual_sdk_http_auth_rejection_suppresses_raw_error_args(monkeypatch, caplog):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(401, json={"errorCode": "InvalidApiKey",
                                        "errorMessage": " ".join(SENSITIVE)})

    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(respond))
    with pytest.raises(sms.SmsDeliveryError) as caught:
        sms._send_live(RECIPIENT, PRIVATE_TEXT)
    assert len(calls) == 1
    _assert_diagnostic(caplog, caught.value, status="rejected", stage="send",
                       category="provider_authentication", provider_code="InvalidApiKey")


@pytest.mark.parametrize("status_code,code", [
    (400, "InvalidApiKey" + PRIVATE_DETAIL), (503, "UnknownError"),
])
def test_actual_sdk_unclassified_http_error_remains_unknown(
    monkeypatch, caplog, status_code, code,
):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status_code, json={"errorCode": code,
                                                "errorMessage": " ".join(SENSITIVE)})

    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(respond))
    with pytest.raises(sms.SmsDeliveryError) as caught:
        sms._send_live(RECIPIENT, PRIVATE_TEXT)
    assert len(calls) == 1
    _assert_diagnostic(caplog, caught.value, status="unknown", stage="send",
                       category="provider_error", provider_code="unclassified")


def test_timeout_keeps_local_request_pending_and_does_not_retry(monkeypatch, caplog):
    calls = _transport(monkeypatch, error=httpx.ReadTimeout(" ".join(SENSITIVE)))
    request_id = str(uuid.uuid4())
    with pytest.raises(sms.SmsDeliveryError) as caught:
        sms.send_contact_sms(_task(), RECIPIENT, "guidance", request_id)
    _assert_diagnostic(caplog, caught.value, status="unknown", stage="send",
                       category="network_timeout", provider_code="unclassified",
                       extra_private=(request_id,))
    with pytest.raises(sms.SmsDeliveryError):
        sms.send_contact_sms(_task(), RECIPIENT, "guidance", request_id)
    assert len(calls) == 1
    assert "result" not in sms._send_requests[request_id]


def test_sdk_response_validation_after_transport_keeps_result_unknown(monkeypatch, caplog):
    malformed = _response()
    malformed["groupInfo"]["count"]["registeredSuccess"] = " ".join(SENSITIVE)
    calls = _transport(monkeypatch, response=malformed)
    with pytest.raises(sms.SmsDeliveryError) as caught:
        sms._send_live(RECIPIENT, PRIVATE_TEXT)
    assert len(calls) == 1
    _assert_diagnostic(caplog, caught.value, status="unknown", stage="response",
                       category="response_invalid", provider_code="unclassified")


def test_nonacceptance_response_is_never_reported_accepted(monkeypatch, caplog):
    calls = _transport(monkeypatch, response=_response(registered_success=0))
    with pytest.raises(sms.SmsDeliveryError) as caught:
        sms._send_live(RECIPIENT, PRIVATE_TEXT)
    assert len(calls) == 1
    _assert_diagnostic(caplog, caught.value, status="unknown", stage="response",
                       category="response_invalid", provider_code="unclassified")


@pytest.mark.parametrize("failure", ["missing_key", "request_validation"])
def test_setup_failure_is_not_sent_and_never_reaches_transport(monkeypatch, caplog, failure):
    calls = _transport(monkeypatch, response=_response())
    message = PRIVATE_TEXT
    if failure == "missing_key":
        monkeypatch.delenv("SOLAPI_API_KEY")
    else:
        message = {"private": " ".join(SENSITIVE)}
    with pytest.raises(sms.SmsDeliveryError) as caught:
        sms._send_live(RECIPIENT, message)
    assert calls == []
    _assert_diagnostic(caplog, caught.value, status="not_sent", stage="setup",
                       category="setup_error", provider_code="unclassified")


def test_independent_diagnostics_get_distinct_server_generated_ids(monkeypatch, caplog):
    _transport(monkeypatch, error=httpx.ReadTimeout(PRIVATE_DETAIL))
    identifiers = set()
    for _ in range(2):
        caplog.clear()
        with pytest.raises(sms.SmsDeliveryError) as caught:
            sms._send_live(RECIPIENT, PRIVATE_TEXT)
        _assert_diagnostic(caplog, caught.value, status="unknown", stage="send",
                           category="network_timeout")
        identifiers.add(caught.value.diagnostic_id)
    assert len(identifiers) == 2


def test_unknown_send_preserves_cloud_pending_without_finish_or_second_send(monkeypatch, caplog):
    for key, value in {
        "VERCEL": "1", "UPSTASH_REDIS_REST_URL": "https://synthetic.upstash.io",
        "UPSTASH_REDIS_REST_TOKEN": "synthetic-guard-token",
        "SMS_GUARD_HMAC_KEY": "z" * 64, "SMS_GUARD_NAMESPACE": "diagnostic-test",
        "SMS_ALLOWED_ORIGINS": "https://pilot.example.com",
        "SMS_MAX_DAILY": "10", "SMS_MAX_MONTHLY": "100",
    }.items():
        monkeypatch.setenv(key, value)
    commands = []

    def redis(config, parts):
        commands.append(parts)
        assert parts[0] == "EVAL" and parts[1] == guard.RESERVE_LUA
        return ["reserved"] if len(commands) == 1 else ["pending"]

    monkeypatch.setattr(guard, "_command", redis)
    calls = _transport(monkeypatch, error=httpx.ReadTimeout(" ".join(SENSITIVE)))
    request_id = str(uuid.uuid4())
    with pytest.raises(sms.SmsDeliveryError) as caught:
        sms.send_contact_sms(_task(), RECIPIENT, "guidance", request_id, "192.0.2.1")
    _assert_diagnostic(caplog, caught.value, status="unknown", stage="send",
                       category="network_timeout",
                       extra_private=(request_id, "192.0.2.1", "synthetic-guard-token"))
    with pytest.raises(sms.SmsDeliveryError):
        sms.send_contact_sms(_task(), RECIPIENT, "guidance", request_id, "192.0.2.1")
    assert len(calls) == 1 and len(commands) == 2
    assert commands[0] == commands[1]
    assert all(parts[1] != guard.FINISH_LUA for parts in commands)
    assert request_id not in json.dumps(commands)


@pytest.mark.parametrize("error", [
    RuntimeError("InvalidApiKey", " ".join(SENSITIVE)),
    Exception("InvalidApiKey " + PRIVATE_DETAIL, PRIVATE_TEXT),
    Exception(" " + "InvalidApiKey", PRIVATE_DETAIL),
    Exception("InvalidApiKey", PRIVATE_DETAIL, PRIVATE_TEXT),
    Exception({"code": "InvalidApiKey", "private": PRIVATE_TEXT}, PRIVATE_DETAIL),
    Exception(PRIVATE_DETAIL),
])
def test_untrusted_exception_shapes_never_become_known_provider_codes(monkeypatch, caplog, error):
    calls = _transport(monkeypatch, error=error)
    with pytest.raises(sms.SmsDeliveryError) as caught:
        sms._send_live(RECIPIENT, PRIVATE_TEXT)
    assert len(calls) == 1
    _assert_diagnostic(caplog, caught.value, status="unknown", stage="send",
                       category="provider_error", provider_code="unclassified")


@pytest.mark.parametrize("error,category", [
    (TimeoutError(" ".join(SENSITIVE)), "network_timeout"),
    (httpx.ConnectError(" ".join(SENSITIVE)), "network_error"),
])
def test_transport_failures_keep_safe_categories(monkeypatch, caplog, error, category):
    calls = _transport(monkeypatch, error=error)
    with pytest.raises(sms.SmsDeliveryError) as caught:
        sms._send_live(RECIPIENT, PRIVATE_TEXT)
    assert len(calls) == 1
    _assert_diagnostic(caplog, caught.value, status="unknown", stage="send",
                       category=category, provider_code="unclassified")


@pytest.mark.parametrize("group_id", ["", "   ", None])
def test_missing_acceptance_identifier_remains_unknown(monkeypatch, caplog, group_id):
    response = _response()
    response["groupInfo"]["groupId"] = group_id
    calls = _transport(monkeypatch, response=response)
    with pytest.raises(sms.SmsDeliveryError) as caught:
        sms._send_live(RECIPIENT, PRIVATE_TEXT)
    assert len(calls) == 1
    _assert_diagnostic(caplog, caught.value, status="unknown", stage="response",
                       category="response_invalid", provider_code="unclassified")


def test_broken_log_sink_still_returns_safe_diagnostic_and_never_retries(monkeypatch):
    calls = _transport(monkeypatch, error=httpx.ReadTimeout(" ".join(SENSITIVE)))

    def broken_log(*args, **kwargs):
        raise RuntimeError(" ".join(SENSITIVE))

    monkeypatch.setattr(logging.getLogger("sms_delivery"), "warning", broken_log)
    request_id = str(uuid.uuid4())
    with pytest.raises(sms.SmsDeliveryError) as caught:
        sms.send_contact_sms(_task(), RECIPIENT, "guidance", request_id)
    assert caught.value.delivery_status == "unknown"
    assert caught.value.category == "network_timeout"
    assert re.fullmatch(r"SMS-[0-9a-f]{12}", caught.value.diagnostic_id)
    assert caught.value.diagnostic_id in str(caught.value)
    assert all(value not in str(caught.value) for value in SENSITIVE)
    with pytest.raises(sms.SmsDeliveryError):
        sms.send_contact_sms(_task(), RECIPIENT, "guidance", request_id)
    assert len(calls) == 1


@pytest.mark.parametrize("padding", ["", " ", "\n", " \t\r\n"])
def test_sdk_signs_with_normalized_credentials_and_sender(monkeypatch, caplog, padding):
    for key, value in {"SOLAPI_API_KEY": API_KEY, "SOLAPI_API_SECRET": API_SECRET,
                       "SOLAPI_SENDER": SENDER}.items():
        monkeypatch.setenv(key, padding + value + padding)
    assert sms.sms_capability()["ready"] is True
    requests = []

    def respond(request):
        requests.append(request)
        scheme, fields = request.headers["Authorization"].split(" ", 1)
        assert scheme == "HMAC-SHA256"
        authorization = dict(field.strip().split("=", 1) for field in fields.split(","))
        assert authorization["ApiKey"] == API_KEY
        expected_signature = hmac.new(
            API_SECRET.encode(),
            (authorization["Date"] + authorization["salt"]).encode(),
            hashlib.sha256,
        ).hexdigest()
        assert hmac.compare_digest(authorization["signature"], expected_signature)
        message = json.loads(request.content)["messages"][0]
        assert message["from"] == SENDER and message["to"] == RECIPIENT
        return httpx.Response(200, json=_response())

    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(respond))
    result = sms.send_contact_sms(_task(), RECIPIENT, "guidance", str(uuid.uuid4()))
    assert result == {"status": "accepted", "provider": "solapi", "message_group_id": GROUP_ID}
    assert len(requests) == 1
    assert not [record for record in caplog.records if record.name == "sms_delivery"]
    assert all(value not in caplog.text for value in SENSITIVE)


@pytest.mark.parametrize("key", ["SOLAPI_API_KEY", "SOLAPI_API_SECRET", "SOLAPI_SENDER"])
@pytest.mark.parametrize("blank", ["", "   ", "\t\r\n"])
def test_empty_normalized_setting_is_not_ready_and_never_sends(monkeypatch, caplog, key, blank):
    monkeypatch.setenv(key, blank)
    calls = _transport(monkeypatch, response=_response())
    capability = sms.sms_capability()
    assert capability["mode"] == "live" and capability["ready"] is False
    with pytest.raises(sms.SmsConfigurationError) as configuration_error:
        sms.send_contact_sms(_task(), RECIPIENT, "guidance", str(uuid.uuid4()))
    assert all(value not in str(configuration_error.value) for value in SENSITIVE)
    with pytest.raises(sms.SmsDeliveryError) as caught:
        sms._send_live(RECIPIENT, PRIVATE_TEXT)
    _assert_diagnostic(caplog, caught.value, status="not_sent", stage="setup",
                       category="setup_error", provider_code="unclassified")
    assert calls == []


def test_normalization_preserves_internal_credential_characters(monkeypatch, caplog):
    key = 'synthetic private-"key"'
    secret = 'synthetic private-"secret"'
    monkeypatch.setenv("SOLAPI_API_KEY", "\r\n " + key + " \t")
    monkeypatch.setenv("SOLAPI_API_SECRET", " \t" + secret + "\r\n ")
    assert sms.sms_capability()["ready"] is True
    calls = []

    def fetcher(auth_parameter, request, data=None):
        calls.append(request)
        assert auth_parameter == {"api_key": key, "api_secret": secret}
        return _response()

    monkeypatch.setattr(sdk_messages, "default_fetcher", fetcher)
    assert sms._send_live(RECIPIENT, PRIVATE_TEXT)["status"] == "accepted"
    assert len(calls) == 1
    assert key not in caplog.text and secret not in caplog.text


def test_padded_credentials_keep_signature_rejection_diagnostics_private(monkeypatch, caplog):
    for key, value in {"SOLAPI_API_KEY": API_KEY, "SOLAPI_API_SECRET": API_SECRET,
                       "SOLAPI_SENDER": SENDER}.items():
        monkeypatch.setenv(key, " \r\n" + value + "\n ")
    calls = _transport(monkeypatch, error=Exception("SignatureDoesNotMatch", " ".join(SENSITIVE)))
    request_id = str(uuid.uuid4())
    with pytest.raises(sms.SmsDeliveryError) as caught:
        sms.send_contact_sms(_task(), RECIPIENT, "guidance", request_id)
    _assert_diagnostic(caplog, caught.value, status="rejected", stage="send",
                       category="provider_authentication", provider_code="SignatureDoesNotMatch",
                       extra_private=(request_id,))
    with pytest.raises(sms.SmsDeliveryError):
        sms.send_contact_sms(_task(), RECIPIENT, "guidance", request_id)
    assert len(calls) == 1
