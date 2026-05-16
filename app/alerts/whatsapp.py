"""
JSEdge - WhatsApp alert channel via Twilio Sandbox.

Uses Twilio's shared sandbox WhatsApp number to deliver alerts.
For a single-user personal tool this is the right choice: free,
no business approval, takes one 'join CODE' message to activate.

Caveats (see also: NEXT.md and the alerts design doc):
    - You must have texted 'join <sandbox-code>' from your phone
      to Twilio's sandbox WhatsApp number ONCE to activate the
      channel. Re-join required after 72 hours of silence.
    - Sandbox number is shared with other Twilio devs. Rate limits
      apply but are generous for personal use (~3 msgs/day).

Public functions:
    send_whatsapp(body)        - send a message to your configured number
    send_test_whatsapp()       - one-off "hello world" probe
"""

import logging
from typing import Optional

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from app.database import get_connection

log = logging.getLogger(__name__)

# Twilio's shared sandbox WhatsApp number. Same for ALL Twilio devs
# worldwide — your phone is what gets routed to your account, not the
# from-number. Format is 'whatsapp:+E.164-number'.
SANDBOX_FROM = "whatsapp:+14155238886"


def _get_settings() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (account_sid, auth_token, whatsapp_number) from settings."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT key, value FROM user_settings "
            "WHERE key IN ('twilio_account_sid', 'twilio_auth_token', 'whatsapp_number')"
        ).fetchall()
    finally:
        conn.close()

    settings = {r["key"]: r["value"] for r in rows}
    return (
        settings.get("twilio_account_sid"),
        settings.get("twilio_auth_token"),
        settings.get("whatsapp_number"),
    )


def send_whatsapp(body: str) -> dict:
    """
    Send a WhatsApp message via Twilio Sandbox to your configured number.

    Returns:
        {"ok": True,  "sid": "<twilio-message-sid>", "status": "queued"}
        {"ok": False, "error": "<short message>"}

    On failure, common causes:
        - Sandbox not joined (or 72-hour window expired): user must
          text 'join <code>' to Twilio's sandbox number from WhatsApp.
        - Wrong phone format: number must be E.164, e.g. +18761234567.
        - Bad credentials: account_sid or auth_token wrong.
    """
    sid, token, to_number = _get_settings()
    if not sid:
        return {"ok": False, "error": "twilio_account_sid not set"}
    if not token:
        return {"ok": False, "error": "twilio_auth_token not set"}
    if not to_number:
        return {"ok": False, "error": "whatsapp_number not set"}

    # E.164 format check (basic). Real format: +<country><number>.
    if not to_number.startswith("+"):
        return {
            "ok": False,
            "error": f"whatsapp_number must start with +. Got: {to_number[:5]}...",
        }

    client = Client(sid, token)

    try:
        msg = client.messages.create(
            from_ = SANDBOX_FROM,
            to    = f"whatsapp:{to_number}",
            body  = body,
        )
        return {"ok": True, "sid": msg.sid, "status": msg.status}
    except TwilioRestException as e:
        # Twilio-specific errors include status code + helpful message.
        err = f"Twilio error {e.code}: {e.msg}"[:200]
        log.exception("Twilio WhatsApp send failed")
        return {"ok": False, "error": err}
    except Exception as e:
        err = str(e)[:200]
        log.exception("Unexpected WhatsApp send failure")
        return {"ok": False, "error": err}


def send_test_whatsapp() -> dict:
    """One-off probe to confirm the Twilio Sandbox wiring works."""
    return send_whatsapp(
        body=(
            "*Hello from JSEdge!* If you're reading this, your "
            "WhatsApp alert channel is working. 🎯"
        ),
    )