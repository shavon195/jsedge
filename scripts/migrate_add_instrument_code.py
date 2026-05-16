"""
JSEdge - Migration: add instrument_code column to stocks table.

The JSE Price History page identifies each stock by a numeric
instrument code (e.g. CARRERAS LIMITED = 39). We need to store this
code on each stock row so we can build URLs for the historical price
scraper.

This migration is idempotent: re-running it is safe.

Usage:
    python scripts/migrate_add_instrument_code.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection


def column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def main() -> None:
    conn = get_connection()
    try:
        if column_exists(conn, "stocks", "instrument_code"):
            print("stocks.instrument_code already exists. Nothing to do.")
            return

        print("Adding instrument_code column to stocks...")
        conn.execute("ALTER TABLE stocks ADD COLUMN instrument_code INTEGER")
        conn.commit()
        print("Done.")

        # Show the resulting schema.
        rows = conn.execute("PRAGMA table_info(stocks)").fetchall()
        for r in rows:
            mark = "  <-- NEW" if r["name"] == "instrument_code" else ""
            print(f"  {r['name']:20s} {r['type']}{mark}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()