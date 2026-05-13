"""
JSEdge - Single-admin authentication.

Protects write routes behind a password gate. Read-only routes
(/, /news listing, /health) stay public.

Design:
    - One admin (you). No user table, no registration, no recovery flow.
    - Password lives in .env (never committed) and is read at module import.
    - Sessions are signed cookies issued by itsdangerous TimestampSigner.
      The cookie value is just the literal string "admin" + a timestamp
      signature. No DB lookup needed to validate.
    - Cookies last 7 days (SESSION_MAX_AGE).
    - Logout simply clears the cookie.

Public API:
    require_admin   - FastAPI dependency; raises 303 redirect to /admin/login
                      when caller is not authenticated.
    is_admin        - bool helper, useful in templates via {{ is_admin }}
    login_user      - check password and return (cookie_value, success)
    SESSION_COOKIE  - the cookie key name, e.g. for set_cookie / delete_cookie.
"""

import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

# Load .env at module import. Safe to call multiple times.
load_dotenv()

ADMIN_PASSWORD  = os.getenv("ADMIN_PASSWORD", "")
SESSION_SECRET  = os.getenv("SESSION_SECRET", "")
SESSION_COOKIE  = "jsedge_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7   # 7 days in seconds

if not ADMIN_PASSWORD:
    # Fail loud rather than silently allowing logins with empty password.
    raise RuntimeError(
        "ADMIN_PASSWORD is not set. Put it in .env at the project root."
    )
if not SESSION_SECRET or len(SESSION_SECRET) < 32:
    raise RuntimeError(
        "SESSION_SECRET is missing or too short (need >=32 chars). "
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )

_signer = TimestampSigner(SESSION_SECRET)


def login_user(password_attempt: str) -> Optional[str]:
    """
    Verify a password attempt and return a signed cookie value on success.

    Returns the signed token string to put into the cookie, or None on
    bad password.
    """
    if password_attempt != ADMIN_PASSWORD:
        return None
    # Token payload is just the literal "admin" - we only have one user.
    # The signer adds a timestamp + HMAC so it can't be forged or replayed
    # beyond SESSION_MAX_AGE.
    return _signer.sign(b"admin").decode("utf-8")


def is_admin(request: Request) -> bool:
    """True if the request carries a valid, unexpired session cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return False
    try:
        _signer.unsign(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return True


def require_admin(request: Request):
    """
    FastAPI dependency. Use with `Depends(require_admin)` on protected
    routes. If the caller isn't logged in, raise a redirect to
    /admin/login with a `next` param so we can bounce back after auth.
    """
    if is_admin(request):
        return True

    # Build a "next" URL so login can send us back where we tried to go.
    next_path = request.url.path
    if request.url.query:
        next_path += "?" + request.url.query

    # We can't return a RedirectResponse from a dependency in a way that
    # FastAPI will short-circuit, so we raise it as a starlette HTTPException
    # subclass instead. Simplest approach: just raise a redirect through
    # FastAPI's `HTTPException` won't work for redirects, so we use a
    # small trick: raise a custom exception and let the route handler
    # surface it. Cleanest way: redirect via raising starlette's
    # `RedirectResponse` won't work as raise either.
    #
    # The reliable approach is: make this dep return a RedirectResponse,
    # and routes that depend on it check the type. But that's clumsy.
    #
    # Cleanest: raise an HTTPException with status 303 and a Location
    # header. FastAPI sends the headers through.
    from fastapi import HTTPException
    raise HTTPException(
        status_code=303,
        detail="Login required.",
        headers={"Location": f"/admin/login?next={next_path}"},
    )