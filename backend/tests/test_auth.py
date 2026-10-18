import time

import httpx
import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner

from app.api.routes.auth import get_http
from app.core.config import get_settings
from app.main import app
from app.services import auth


@pytest.fixture
def oauth(monkeypatch):
    """Turn sign-in on with fake credentials."""
    s = get_settings()
    monkeypatch.setattr(s, "github_oauth_client_id", "cid")
    monkeypatch.setattr(s, "github_oauth_client_secret", "csecret")
    monkeypatch.setattr(s, "session_secret", "x" * 40)
    monkeypatch.setattr(s, "allowed_github_users", "")
    monkeypatch.setattr(s, "public_base_url", "")
    return s


def fake_github(login="octocat", token="gho_token", fail_exchange=False):
    seen = {"exchange": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/oauth/access_token":
            seen["exchange"] = dict(httpx.QueryParams(request.content.decode()))
            if fail_exchange:
                return httpx.Response(200, json={"error": "bad_verification_code"})
            return httpx.Response(200, json={"access_token": token})
        if request.url.path == "/user":
            assert request.headers["authorization"] == f"Bearer {token}"
            return httpx.Response(200, json={"login": login, "id": 7, "name": "Octo Cat",
                                             "avatar_url": "https://a/b.png"})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_http] = lambda: client
    return seen


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_http, None)


def sign_in(c: TestClient, **kw):
    """Run the whole authorization-code flow and leave the session cookie in `c`."""
    seen = fake_github(**kw)
    login = c.get("/api/auth/login", follow_redirects=False)
    assert login.status_code == 302
    state = httpx.URL(login.headers["location"]).params["state"]
    cb = c.get(f"/api/auth/callback?code=abc&state={state}", follow_redirects=False)
    return cb, seen


def test_auth_disabled_keeps_app_open(client):
    assert client.get("/api/auth/config").json()["enabled"] is False
    assert client.get("/api/repositories").status_code == 200
    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is False and me["auth_enabled"] is False
    assert client.get("/api/auth/login", follow_redirects=False).status_code == 404


def test_protected_routes_require_sign_in(client, oauth):
    assert client.get("/api/auth/config").json()["enabled"] is True
    assert client.get("/api/repositories").status_code == 401
    assert client.get("/api/diagnoses").status_code == 401
    assert client.get("/api/stats").status_code == 401
    assert client.get("/api/audit").status_code == 401
    assert client.post("/api/diagnose-log", json={"log": "x"}).status_code == 401
    # public endpoints stay public
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_login_redirects_to_github_with_state_and_redirect_uri(client, oauth):
    r = client.get("/api/auth/login", follow_redirects=False)
    url = httpx.URL(r.headers["location"])
    assert url.host == "github.com" and url.path == "/login/oauth/authorize"
    assert url.params["client_id"] == "cid"
    assert url.params["redirect_uri"].endswith("/api/auth/callback")
    assert url.params["state"]
    assert "httponly" in r.headers["set-cookie"].lower()
    assert "scope" not in url.params  # we ask for no permissions at all


def test_full_flow_sets_session_and_unlocks_api(client, oauth):
    cb, seen = sign_in(client)
    assert cb.status_code == 302 and cb.headers["location"] == "/"
    assert seen["exchange"]["client_secret"] == "csecret" and seen["exchange"]["code"] == "abc"
    cookie = cb.headers["set-cookie"].lower()
    assert "devpilot_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie

    me = client.get("/api/auth/me").json()
    assert me["authenticated"] and me["user"]["login"] == "octocat"
    assert client.get("/api/repositories").status_code == 200

    client.post("/api/auth/logout")
    assert client.get("/api/repositories").status_code == 401


def test_writes_need_the_csrf_header(client, oauth):
    sign_in(client)
    body = {"full_name": "octocat/hello"}
    assert client.post("/api/repositories", json=body).status_code == 403
    ok = client.post("/api/repositories", json=body, headers={"X-Requested-With": "devpilot"})
    assert ok.status_code == 201


def test_callback_rejects_missing_or_tampered_state(client, oauth):
    fake_github()
    assert client.get("/api/auth/callback?code=abc&state=nope").status_code == 400
    client.get("/api/auth/login", follow_redirects=False)
    assert client.get("/api/auth/callback?code=abc&state=wrong").status_code == 400
    assert client.get("/api/repositories").status_code == 401


def test_failed_code_exchange_does_not_sign_in(client, oauth):
    cb, _ = sign_in(client, fail_exchange=True)
    assert cb.headers["location"] == "/?login_error=failed"
    assert client.get("/api/repositories").status_code == 401


def test_allow_list_blocks_other_accounts(client, oauth, monkeypatch):
    monkeypatch.setattr(oauth, "allowed_github_users", "dewwbe, someone")
    cb, _ = sign_in(client, login="octocat")
    assert cb.headers["location"] == "/?login_error=not_allowed"
    assert client.get("/api/repositories").status_code == 401

    cb, _ = sign_in(client, login="Dewwbe")  # case-insensitive
    assert cb.headers["location"] == "/"
    assert client.get("/api/repositories").status_code == 200


def test_user_cancelling_on_github_returns_to_app(client, oauth):
    r = client.get("/api/auth/callback?error=access_denied", follow_redirects=False)
    assert r.headers["location"] == "/?login_error=cancelled"


def test_forged_and_expired_sessions_are_rejected(client, oauth, monkeypatch):
    client.cookies.set("devpilot_session", "forged.value.here")
    assert client.get("/api/repositories").status_code == 401

    # A genuine, correctly signed cookie that was issued 13 hours ago (the TTL is 12).
    with monkeypatch.context() as m:
        m.setattr(TimestampSigner, "get_timestamp", lambda self: int(time.time()) - 13 * 3600)
        old = auth.sign_session(auth.User(login="octocat"))
    client.cookies.set("devpilot_session", old)
    assert client.get("/api/repositories").status_code == 401

    fresh = auth.sign_session(auth.User(login="octocat"))
    client.cookies.set("devpilot_session", fresh)
    assert client.get("/api/repositories").status_code == 200


def test_session_signed_with_another_secret_is_rejected(client, oauth, monkeypatch):
    token = auth.sign_session(auth.User(login="octocat"))
    monkeypatch.setattr(oauth, "session_secret", "y" * 40)
    client.cookies.set("devpilot_session", token)
    assert client.get("/api/repositories").status_code == 401


def test_reviewer_identity_comes_from_the_session_not_the_request(client, oauth):
    from app.models.entities import RiskLevel
    from tests.test_api import _seed_fix

    sign_in(client, login="octocat")
    fix_id = _seed_fix(RiskLevel.low)
    r = client.post(f"/api/fixes/{fix_id}/decision",
                    json={"decision": "approved", "reviewer": "someone-else"},
                    headers={"X-Requested-With": "devpilot"})
    assert r.status_code == 200 and r.json()["decided_by"] == "octocat"
    actors = {e["actor"] for e in client.get("/api/audit").json() if e["action"] == "fix.approved"}
    assert actors == {"octocat"}


def test_https_base_url_marks_cookies_secure(client, oauth, monkeypatch):
    monkeypatch.setattr(oauth, "public_base_url", "https://devpilot.example.com")
    r = client.get("/api/auth/login", follow_redirects=False)
    assert "secure" in r.headers["set-cookie"].lower()
    assert httpx.URL(r.headers["location"]).params["redirect_uri"] == \
        "https://devpilot.example.com/api/auth/callback"
