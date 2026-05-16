"""
JSEdge - Inspect user_settings without exposing secret values.

Shows all settings rows. For sensitive keys (anything ending in
'_api_key', 'secret', 'password'), only the length and a masked
preview is shown — never the full value.

Usage:
    python scripts/check_settings.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection


SENSITIVE_SUFFIXES = ("_api_key", "_secret", "_password", "_token", "_sid")
SENSITIVE_KEYS = ("email_address", "whatsapp_number")

def is_sensitive(key: str) -> bool:
    if key in SENSITIVE_KEYS:
        return True
    return any(key.endswith(suf) for suf in SENSITIVE_SUFFIXES)

def mask(value: str) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 8:
        return "***"
    return value[:4] + "..." + value[-4:]


def main() -> None:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT key, value, updated_at FROM user_settings ORDER BY key"
        ).fetchall()

        if not rows:
            print("No user_settings rows.")
            return

        print(f"{len(rows)} setting(s):")
        print()
        for r in rows:
            key = r["key"]
            val = r["value"]
            updated = r["updated_at"]
            if is_sensitive(key):
                display = f"{mask(val)}  ({len(val)} chars)"
            else:
                display = repr(val)
            print(f"  {key:24s} = {display}")
            print(f"    last updated: {updated}")
            print()
    finally:
        conn.close()


if __name__ == "__main__":
    main()