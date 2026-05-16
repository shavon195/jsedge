"""
JSEdge - Securely save an API key to the user_settings table.

Prompts for the key value (input is hidden so it doesn't show on screen
or in shell history) and saves it under the given setting key.

Usage:
    python scripts/set_api_key.py gemini_api_key
    python scripts/set_api_key.py claude_api_key
"""

import getpass
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection


VALID_KEYS = {
    "gemini_api_key", "claude_api_key", "resend_api_key",
    "twilio_account_sid", "twilio_auth_token",
    "email_address", "whatsapp_number",
}


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/set_api_key.py <setting_key>")
        print(f"Valid setting keys: {', '.join(sorted(VALID_KEYS))}")
        return

    setting_key = sys.argv[1]
    if setting_key not in VALID_KEYS:
        print(f"ERROR: {setting_key!r} is not a valid setting key.")
        print(f"Valid setting keys: {', '.join(sorted(VALID_KEYS))}")
        return

    # getpass hides input as you type (like a password prompt).
    new_value = getpass.getpass(f"Paste value for {setting_key}: ").strip()
    if not new_value:
        print("Empty value — nothing saved.")
        return

    conn = get_connection()
    try:
        # user_settings has key as PRIMARY KEY — use UPSERT.
        conn.execute(
            """
            INSERT INTO user_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = datetime('now')
            """,
            (setting_key, new_value),
        )
        conn.commit()

        # Verify it took and show only a masked preview.
        row = conn.execute(
            "SELECT value FROM user_settings WHERE key = ?",
            (setting_key,),
        ).fetchone()
        if row and row["value"] == new_value:
            masked = new_value[:4] + "..." + new_value[-4:] if len(new_value) > 8 else "***"
            print(f"Saved {setting_key} = {masked}")
        else:
            print("ERROR: value did not save correctly.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()