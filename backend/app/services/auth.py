"""Sign in with GitHub (OAuth 2.0 authorization-code flow) and signed session cookies.

Flow: /api/auth/login sets a one-time `state` cookie and redirects to GitHub; GitHub redirects
back to /api/auth/callback with `code` and `state`; we verify `state`, exchange the code for an
access token (server to server, using the client secret), read the user's profile, check the
optional allow-list, and set a signed, HttpOnly session cookie. We request no scopes: the token is
used once, only to read the public profile, and is never stored.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import get_settings

SESSION_COOKIE = "devpilot_session"
STATE_COOKIE = "devpilot_oauth_state"
_SALT = "devpilot-session-v1"
_STATE_SALT = "devpilot-oauth-state-v1"


@dataclass(frozen=True)
class User:
    login: str
    name: str = ""
    avatar_url: str = ""
    github_id: int = 0
    authenticated: bool = True


ANONYMOUS = User(login="anonymous", name="Anonymous (auth disabled)", authenticated=False)


def auth_enabled() -> bool:
    s = get_settings()
    return bool(s.github_oauth_client_id and s.github_oauth_client_secret and s.session_secret)


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt=salt)


def sign_session(user: User) -> str:
    return _serializer(_SALT).dumps({"login": user.login, "name": user.name,
                                     "avatar_url": user.avatar_url, "id": user.github_id})


def read_session(token: str | None) -> User | None:
    if not token or not auth_enabled():
        return None
    try:
        data = _serializer(_SALT).loads(token, max_age=get_settings().session_ttl_hours * 3600)
    except (BadSignature, SignatureExpired):
        return None
    return User(login=data["login"], name=data.get("name", ""),
                avatar_url=data.get("avatar_url", ""), github_id=data.get("id", 0))


def new_state() -> tuple[str, str]:
    """A random OAuth `state` value and its signed form for the cookie (CSRF protection)."""
    state = secrets.token_urlsafe(24)
    return state, _serializer(_STATE_SALT).dumps(state)


def state_is_valid(state: str | None, cookie: str | None) -> bool:
    if not state or not cookie:
        return False
    try:
        expected = _serializer(_STATE_SALT).loads(cookie, max_age=600)  # 10 minutes to finish
    except (BadSignature, SignatureExpired):
        return False
    return secrets.compare_digest(expected, state)


def allowed(login: str) -> bool:
    raw = get_settings().allowed_github_users
    allow = {u.strip().lower() for u in raw.split(",") if u.strip()}
    return not allow or login.lower() in allow


def base_url(request: Request) -> str:
    """Public origin used for the OAuth redirect URI. Prefer the configured value; otherwise trust
    the proxy headers (nginx/Caddy/ingress set X-Forwarded-Proto and Host)."""
    configured = get_settings().public_base_url.rstrip("/")
    if configured:
        return configured
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "localhost"
    return f"{proto}://{host}"


def authorize_url(state: str, redirect_uri: str) -> str:
    s = get_settings()
    q = urlencode({"client_id": s.github_oauth_client_id, "redirect_uri": redirect_uri,
                   "state": state, "allow_signup": "true"})
    return f"{s.github_oauth_base}/login/oauth/authorize?{q}"


def exchange_code(code: str, redirect_uri: str, http: httpx.Client | None = None) -> str:
    """Server-to-server code -> access token exchange. Raises on any failure."""
    s = get_settings()
    client = http or httpx.Client(timeout=15)
    r = client.post(f"{s.github_oauth_base}/login/oauth/access_token",
                    headers={"Accept": "application/json"},
                    data={"client_id": s.github_oauth_client_id,
                          "client_secret": s.github_oauth_client_secret,
                          "code": code, "redirect_uri": redirect_uri})
    r.raise_for_status()
    body = r.json()
    token = body.get("access_token")
    if not token:
        raise ValueError(body.get("error_description") or body.get("error") or "no access token")
    return token


def fetch_user(token: str, http: httpx.Client | None = None) -> User:
    s = get_settings()
    api = s.github_api_base.rstrip("/")
    client = http or httpx.Client(timeout=15)
    r = client.get(f"{api}/user", headers={"Authorization": f"Bearer {token}",
                                           "Accept": "application/vnd.github+json"})
    r.raise_for_status()
    d = r.json()
    return User(login=d["login"], name=d.get("name") or "", avatar_url=d.get("avatar_url") or "",
                github_id=int(d.get("id", 0)))


# ---------------- FastAPI dependencies ----------------

def current_user(request: Request) -> User | None:
    """The signed-in user, or None. With auth disabled everyone is the anonymous local user."""
    if not auth_enabled():
        return ANONYMOUS
    return read_session(request.cookies.get(SESSION_COOKIE))


def require_user(request: Request, user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(401, "Sign in required")
    # Cookie-authenticated writes must come from our own frontend (defence in depth on top of
    # SameSite=Lax): a cross-site form post cannot set a custom header.
    if (auth_enabled() and request.method not in ("GET", "HEAD", "OPTIONS")
            and request.headers.get("x-requested-with") != "devpilot"):
        raise HTTPException(403, "Missing X-Requested-With header")
    return user
