"""Sign in with GitHub (OAuth 2.0). See app/services/auth.py for the flow."""
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.core.logging import log
from app.services import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_http() -> httpx.Client:
    """Dependency so tests can swap in a mock transport."""
    return httpx.Client(timeout=15)


def _secure(request: Request) -> bool:
    return auth.base_url(request).startswith("https://")


@router.get("/config")
def auth_config():
    return {"enabled": auth.auth_enabled(), "provider": "github"}


@router.get("/login")
def login(request: Request):
    if not auth.auth_enabled():
        raise HTTPException(404, "Authentication is not configured")
    state, signed = auth.new_state()
    redirect_uri = f"{auth.base_url(request)}/api/auth/callback"
    resp = RedirectResponse(auth.authorize_url(state, redirect_uri), status_code=302)
    resp.set_cookie(auth.STATE_COOKIE, signed, max_age=600, httponly=True, samesite="lax",
                    secure=_secure(request), path="/api/auth")
    return resp


@router.get("/callback")
def callback(request: Request, code: str = "", state: str = "", error: str = "",
             http: httpx.Client = Depends(get_http)):
    if not auth.auth_enabled():
        raise HTTPException(404, "Authentication is not configured")
    if error:  # the user clicked "Cancel" on GitHub
        return RedirectResponse("/?login_error=cancelled", status_code=302)
    if not auth.state_is_valid(state, request.cookies.get(auth.STATE_COOKIE)):
        raise HTTPException(400, "Invalid or expired sign-in state. Please try again.")

    redirect_uri = f"{auth.base_url(request)}/api/auth/callback"
    try:
        token = auth.exchange_code(code, redirect_uri, http)
        user = auth.fetch_user(token, http)
    except Exception as exc:  # noqa: BLE001  (bad code, GitHub outage, wrong client secret)
        log.warning("oauth_failed", error=str(exc)[:200])
        return RedirectResponse("/?login_error=failed", status_code=302)

    if not auth.allowed(user.login):
        log.warning("oauth_user_not_allowed", login=user.login)
        return RedirectResponse("/?login_error=not_allowed", status_code=302)

    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(auth.SESSION_COOKIE, auth.sign_session(user),
                    max_age=get_settings().session_ttl_hours * 3600, httponly=True,
                    samesite="lax", secure=_secure(request), path="/")
    resp.delete_cookie(auth.STATE_COOKIE, path="/api/auth")
    log.info("oauth_login", login=user.login)
    return resp


@router.get("/me")
def me(user: auth.User | None = Depends(auth.current_user)):
    """Always 200 so the frontend can decide what to show without console errors."""
    if user is None:
        return {"authenticated": False, "auth_enabled": True, "user": None}
    # With sign-in off, current_user is the anonymous local user and authenticated is False.
    return {"authenticated": user.authenticated, "auth_enabled": auth.auth_enabled(),
            "user": {"login": user.login, "name": user.name, "avatar_url": user.avatar_url}}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"status": "signed out"}
