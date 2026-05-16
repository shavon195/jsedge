"""
JSEdge - Email alert channel via Resend.

Wraps Resend's Python SDK with JSEdge-specific defaults:
    - Uses 'onboarding@resend.dev' as the FROM address (Resend's
      shared sender that works without domain verification — fine
      for a single-user personal tool).
    - Pulls the API key + recipient email from the user_settings DB
      so they're never hard-coded.

Public functions:
    send_email(subject, html_body) - send to your configured email
    send_test_email()              - one-off "hello world" probe
"""

import logging
from typing import Optional

import resend

from app.database import get_connection

log = logging.getLogger(__name__)

# Resend's shared sender. Mail goes out from this address by default.
# To send from "alerts@jsedge.com" we'd need to verify a domain; not
# needed for personal use.
DEFAULT_FROM = "JSEdge <onboarding@resend.dev>"


def _get_settings() -> tuple[Optional[str], Optional[str]]:
    """Return (api_key, recipient_email) from user_settings, or (None, None)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT key, value FROM user_settings "
            "WHERE key IN ('resend_api_key', 'email_address')"
        ).fetchall()
    finally:
        conn.close()

    settings = {r["key"]: r["value"] for r in rows}
    return settings.get("resend_api_key"), settings.get("email_address")


def send_email(subject: str, html_body: str) -> dict:
    """
    Send an email via Resend to your configured recipient.

    Returns a dict:
        {"ok": True,  "id": "<resend-message-id>"}    on success
        {"ok": False, "error": "<short message>"}     on failure

    Errors are logged but never raised — the caller should check 'ok'
    and decide what to do (e.g. retry, fall back to WhatsApp).
    """
    api_key, to_email = _get_settings()
    if not api_key:
        return {"ok": False, "error": "resend_api_key not set in user_settings"}
    if not to_email:
        return {"ok": False, "error": "email_address not set in user_settings"}

    resend.api_key = api_key

    try:
        result = resend.Emails.send({
            "from":    DEFAULT_FROM,
            "to":      to_email,
            "subject": subject,
            "html":    html_body,
        })
        # Resend returns {'id': '<uuid>'} on success.
        msg_id = result.get("id") if isinstance(result, dict) else None
        return {"ok": True, "id": msg_id}
    except Exception as e:
        err = str(e)[:200]
        log.exception("Resend send failed")
        return {"ok": False, "error": err}


def send_test_email() -> dict:
    """One-off probe to confirm the Resend wiring works."""
    return send_email(
        subject="JSEdge - test email",
        html_body=(
            "<h2>Hello from JSEdge!</h2>"
            "<p>If you're reading this in your inbox, "
            "your email alert channel is working.</p>"
            "<p style='color:#64748b;font-size:12px;'>"
            "This is a test message sent via the Resend integration.</p>"
        ),
    )