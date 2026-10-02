"""Offline build-gate checks: genuine SDK signing, fixed GET, no SMS or Redis."""

import hashlib
import hmac
import json
import logging
from pathlib import Path
import runpy
import socket
import sys
import traceback

import httpx
import pytest
from solapi import SolapiMessageService

import deployment_catalog
import sms_cloud_guard as guard
import sms_service as sms


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_vercel_catalog.py"
BALANCE_URL = "https://api.solapi.com/cash/v1/balance"
API_KEY = "synthetic-preflight-private-key"
API_SECRET = "synthetic-preflight-private-secret"
SENDER = "0212345678"
PRIVATE_BODY = "synthetic-preflight-private-response"
PRIVATE_TOKEN = "synthetic-preflight-guard-token"
SENSITIVE = (API_KEY, API_SECRET, SENDER, PRIVATE_BODY, PRIVATE_TOKEN)
CATALOG_MARKER = "synthetic-catalog-built"


@pytest.fixture(autouse=True)
def offline_build(monkeypatch, caplog):
    settings = {
        "VERCEL": "1", "SMS_AUTH_PREFLIGHT": "1", "SMS_MODE": "live",
        "SOLAPI_API_KEY": " \r\n" + API_KEY + "\t ",
        "SOLAPI_API_SECRET": "\t " + API_SECRET + " \r\n",
        "SOLAPI_SENDER": " \n" + SENDER + "\r\n ",
        "UPSTASH_REDIS_REST_URL": "https://synthetic-preflight.upstash.io",
        "UPSTASH_REDIS_REST_TOKEN": PRIVATE_TOKEN,
        "SMS_GUARD_HMAC_KEY": "s" * 64, "SMS_GUARD_NAMESPACE": "preflight-test",
        "SMS_ALLOWED_ORIGINS": "https://pilot.example.com",
        "SMS_MAX_DAILY": "10", "SMS_MAX_MONTHLY": "100",
    }
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "path", list(sys.path))
    caplog.set_level(logging.DEBUG)

    def forbidden(*args, **kwargs):
        pytest.fail("Preflight tests must not perform real network, SMS, or guard operations")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(httpx, "HTTPTransport", forbidden)
    monkeypatch.setattr(SolapiMessageService, "send", forbidden)
    monkeypatch.setattr(sms, "_send_live", forbidden)
    monkeypatch.setattr(sms, "send_contact_sms", forbidden)
    for name in ("reserve", "finish", "_command"):
        monkeypatch.setattr(guard, name, forbidden)
    builds = []

    def build(source, destination):
        builds.append((source, destination))
        return CATALOG_MARKER

    monkeypatch.setattr(deployment_catalog, "build_catalog", build)
    return builds


def _balance():
    return {"balance": 123.45, "point": 0, "private": " ".join(SENSITIVE)}


def _http(monkeypatch, *, status=200, payload=None, content=None, error=None, headers=None):
    requests, clients, transports = [], [], []
    actual_client = httpx.Client

    def respond(request):
        requests.append(request)
        assert request.method == "GET" and str(request.url) == BALANCE_URL
        assert request.content == b""
        scheme, fields = request.headers["Authorization"].split(" ", 1)
        assert scheme == "HMAC-SHA256"
        authorization = dict(field.strip().split("=", 1) for field in fields.split(","))
        assert authorization["ApiKey"] == API_KEY
        expected = hmac.new(
            API_SECRET.encode(),
            (authorization["Date"] + authorization["salt"]).encode(),
            hashlib.sha256,
        ).hexdigest()
        assert hmac.compare_digest(authorization["signature"], expected)
        if error is not None:
            raise error
        if content is not None:
            return httpx.Response(status, content=content, headers=headers)
        return httpx.Response(status, json=payload, headers=headers)

    def transport(**kwargs):
        transports.append(kwargs)
        assert kwargs.get("retries") == 0
        return httpx.MockTransport(respond)

    def client(*args, **kwargs):
        clients.append(kwargs)
        assert kwargs["timeout"] == 15
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        return actual_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "HTTPTransport", transport)
    monkeypatch.setattr(httpx, "Client", client)
    return requests, clients, transports


def _run():
    runpy.run_path(str(SCRIPT), run_name="__main__")


def _assert_private(capsys, caplog, error=None):
    captured = capsys.readouterr()
    exposed = captured.out + captured.err + caplog.text
    if error is not None:
        exposed += str(error) + "".join(traceback.format_exception(error))
    for value in SENSITIVE:
        assert value not in exposed
    assert all(record.exc_info is None and record.exc_text is None for record in caplog.records)
    return captured.out + captured.err


def test_opted_in_build_authenticates_with_sdk_signature_then_builds(
    monkeypatch, offline_build, capsys, caplog,
):
    requests, clients, transports = _http(monkeypatch, payload=_balance())
    _run()
    assert len(requests) == len(clients) == len(transports) == len(offline_build) == 1
    output = _assert_private(capsys, caplog)
    assert "SMS auth preflight: auth_verified http_status=200" in output
    assert output.index("auth_verified") < output.index(CATALOG_MARKER)
    assert "123.45" not in output and '"point"' not in output


@pytest.mark.parametrize("vercel,opt_in", [
    (None, None), (None, "1"), ("0", "1"), ("1", None), ("1", "0"), ("1", "true"),
])
def test_build_without_explicit_cloud_opt_in_has_no_preflight_network(
    monkeypatch, offline_build, capsys, caplog, vercel, opt_in,
):
    for key, value in {"VERCEL": vercel, "SMS_AUTH_PREFLIGHT": opt_in}.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    _run()
    assert len(offline_build) == 1
    output = _assert_private(capsys, caplog)
    assert CATALOG_MARKER in output and "SMS auth preflight" not in output


@pytest.mark.parametrize("status,code", [
    (401, "SignatureDoesNotMatch"), (403, "InvalidApiKey"),
    (400, "InvalidApiKey" + PRIVATE_BODY), (429, "TooManyRequests"),
    (500, "UnknownError"), (503, PRIVATE_BODY), (204, PRIVATE_BODY),
])
def test_non_200_preflight_blocks_catalog_and_suppresses_response(
    monkeypatch, offline_build, capsys, caplog, status, code,
):
    requests, _, _ = _http(monkeypatch, status=status,
                           payload={"errorCode": code, "errorMessage": " ".join(SENSITIVE)})
    with pytest.raises(SystemExit) as caught:
        _run()
    assert caught.value.code and len(requests) == 1 and offline_build == []
    output = _assert_private(capsys, caplog, caught.value)
    safe_code = code if code in ("SignatureDoesNotMatch", "InvalidApiKey", "TooManyRequests") else "unclassified"
    assert f"http_status={status} provider_code={safe_code}" in output
    assert "auth_verified" not in output
    assert CATALOG_MARKER not in output


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirects_are_not_followed_and_block_build(
    monkeypatch, offline_build, capsys, caplog, status,
):
    requests, _, _ = _http(monkeypatch, status=status, payload=_balance(),
                           headers={"Location": "https://private-redirect.example/" + PRIVATE_BODY})
    with pytest.raises(SystemExit) as caught:
        _run()
    assert caught.value.code and len(requests) == 1 and offline_build == []
    _assert_private(capsys, caplog, caught.value)


@pytest.mark.parametrize("payload", [
    None, [], {}, {"balance": 1}, {"point": 0},
    {"balance": "123.45", "point": 0}, {"balance": 1, "point": "0"},
    {"balance": None, "point": 0}, {"balance": 1, "point": None},
    {"balance": True, "point": 0}, {"balance": 1, "point": False},
])
def test_malformed_success_schema_blocks_build(
    monkeypatch, offline_build, capsys, caplog, payload,
):
    requests, _, _ = _http(monkeypatch, payload=payload)
    with pytest.raises(SystemExit) as caught:
        _run()
    assert caught.value.code and len(requests) == 1 and offline_build == []
    output = _assert_private(capsys, caplog, caught.value)
    assert "http_status=200 provider_code=unclassified" in output
    assert "auth_verified" not in output


@pytest.mark.parametrize("content", [
    "not-json " + " ".join(SENSITIVE),
    '{"balance":NaN,"point":0}', '{"balance":Infinity,"point":0}',
    '{"balance":1,"point":-Infinity}',
])
def test_invalid_json_or_nonfinite_amounts_block_build(
    monkeypatch, offline_build, capsys, caplog, content,
):
    requests, _, _ = _http(monkeypatch, content=content)
    with pytest.raises(SystemExit) as caught:
        _run()
    assert caught.value.code and len(requests) == 1 and offline_build == []
    _assert_private(capsys, caplog, caught.value)


@pytest.mark.parametrize("error", [
    httpx.ReadTimeout(" ".join(SENSITIVE)),
    httpx.ConnectError(" ".join(SENSITIVE)),
])
def test_network_failure_is_safe_and_not_retried(
    monkeypatch, offline_build, capsys, caplog, error,
):
    requests, _, _ = _http(monkeypatch, error=error)
    with pytest.raises(SystemExit) as caught:
        _run()
    assert caught.value.code and len(requests) == 1 and offline_build == []
    output = _assert_private(capsys, caplog, caught.value)
    assert "http_status=0 provider_code=unclassified" in output
    assert "auth_verified" not in output


@pytest.mark.parametrize("key", ["SOLAPI_API_KEY", "SOLAPI_API_SECRET", "SOLAPI_SENDER"])
@pytest.mark.parametrize("value", [None, " \t\r\n"])
def test_missing_or_blank_settings_block_build_before_http(
    monkeypatch, offline_build, capsys, caplog, key, value,
):
    if value is None:
        monkeypatch.delenv(key)
    else:
        monkeypatch.setenv(key, value)
    with pytest.raises(SystemExit) as caught:
        _run()
    assert caught.value.code and offline_build == []
    _assert_private(capsys, caplog, caught.value)
