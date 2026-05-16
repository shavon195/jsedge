"""
JSEdge - User settings data access.

Thin wrapper around the user_settings table for the /settings page.
Handles masking of sensitive values so they never leave the server in
their raw form unless the user explicitly clicks Update.

Public functions:
    list_settings()         - return all settings (masked) for the UI
    get_setting(key)        - raw value for one key, or None
    save_setting(key, val)  - upsert one setting
    is_sensitive(key)       - bool, matches set_api_key.py conventions
"""

from typing import Optional

from app.database import get_connection


# Same conventions as scripts/check_settings.py — keep in sync.
SENSITIVE_SUFFIXES = ("_api_key", "_secret", "_password", "_token", "_sid")
SENSITIVE_KEYS     = ("email_address", "whatsapp_number")

# Keys the /settings UI exposes for editing. Order matters — this is
# also the display order on the page. Anything in user_settings but
# not listed here stays out of the UI (e.g. internal flags).
EDITABLE_KEYS = [
    ("email_address",       "Email address",        "Where alerts go."),
    ("whatsapp_number",     "WhatsApp number",      "E.164 format, e.g. +18761234567."),
    ("resend_api_key",      "Resend API key",       "For sending email alerts."),
    ("twilio_account_sid",  "Twilio Account SID",   "Starts with AC..."),
    ("twilio_auth_token",   "Twilio Auth Token",    "From Twilio Console > Account."),
    ("gemini_api_key",      "Gemini API key",       "For AI news summaries."),
    ("claude_api_key",      "Claude API key",       "Optional — Anthropic Claude."),
]


def is_sensitive(key: str) -> bool:
    """True if the value should be masked when displayed."""
    if key in SENSITIVE_KEYS:
        return True
    return any(key.endswith(suf) for suf in SENSITIVE_SUFFIXES)


def _mask(value: str) -> str:
    """Mask a sensitive value to 'XXXX...XXXX (N chars)' form."""
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def get_setting(key: str) -> Optional[str]:
    """Return raw value or None if unset."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM user_settings WHERE key = ?",
            (key,),
        ).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def save_setting(key: str, value: str) -> None:
    """Upsert one setting. Empty value is allowed (clears the setting)."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO user_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET "
            "    value = excluded.value, "
            "    updated_at = datetime('now')",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def list_settings() -> list[dict]:
    """
    Return all editable settings for the /settings page.

    Each dict has:
        key         - the storage key
        label       - human-friendly name
        hint        - one-line help text
        is_set      - True if the value is non-empty
        is_sensitive- True if the displayed value should be masked
        display     - masked or plain value to show
        length      - char count (for masked previews)
        updated_at  - timestamp (or None)
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT key, value, updated_at FROM user_settings"
        ).fetchall()
    finally:
        conn.close()

    by_key = {r["key"]: r for r in rows}

    result = []
    for key, label, hint in EDITABLE_KEYS:
        row = by_key.get(key)
        value = row["value"] if row else ""
        sensitive = is_sensitive(key)
        result.append({
            "key":          key,
            "label":        label,
            "hint":         hint,
            "is_set":       bool(value),
            "is_sensitive": sensitive,
            "display":      _mask(value) if sensitive else value,
            "length":       len(value) if value else 0,
            "updated_at":   row["updated_at"] if row else None,
        })
    return result