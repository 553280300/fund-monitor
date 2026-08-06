"""GitHub config sync: token path, gh CLI fallback, and API endpoints."""

import base64
import json

import httpx

from fund_monitor import ghconfig


def _patched_client(monkeypatch, transport):
    original = httpx.Client
    monkeypatch.setattr(
        ghconfig.httpx,
        "Client",
        lambda **kwargs: original(transport=transport, **kwargs),
    )


def test_sync_via_token_pushes_encoded_content(monkeypatch) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"sha": "abc123"})
        return httpx.Response(200, json={"commit": {"sha": "new123"}})

    _patched_client(monkeypatch, httpx.MockTransport(handler))

    message = ghconfig.sync_config("assets: []\n", repo="owner/repo", token="ghp_token")

    assert "GitHub Token" in message
    assert len(calls) == 2
    get_call, put_call = calls
    assert "owner/repo" in str(get_call.url)
    payload = json.loads(put_call.content)
    assert payload["message"] == "Update monitor config from local panel"
    assert payload["sha"] == "abc123"
    assert base64.b64decode(payload["content"]).decode() == "assets: []\n"
    assert put_call.headers["authorization"] == "Bearer ghp_token"


def test_sync_via_token_reports_bad_credentials(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    _patched_client(monkeypatch, httpx.MockTransport(handler))

    try:
        ghconfig.sync_config("x", token="bad")
    except RuntimeError as error:
        assert "Token 无效" in str(error)
    else:
        raise AssertionError("expected RuntimeError for bad token")


def test_sync_falls_back_to_gh_cli_without_token(monkeypatch) -> None:
    captured: list[str] = []

    def fake_gh(*args: str):
        captured.append(" ".join(args))

        class Result:
            pass

        result = Result()
        result.returncode = 0
        result.stdout = "sha123" if "--jq" in args else ""
        result.stderr = ""
        return result

    monkeypatch.setattr(ghconfig, "_run_gh", fake_gh)
    message = ghconfig.sync_config("x", repo="owner/repo", token=None)

    assert "gh CLI" in message
    assert any("owner/repo/contents/headless/config.yaml" in call for call in captured)
