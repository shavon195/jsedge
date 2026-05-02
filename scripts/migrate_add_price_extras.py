"""
JSEdge — Migration: add price-extras columns to `prices_daily`.

Adds these columns to support full ranking:
    - todays_range  : intraday "low - high" string (e.g., "2.85 - 3.35")
    - week52_range  : 52-week "low - high" string  (e.g., "2.55 - 4.78")
    - div_prev_year : dividends paid in previous fiscal year
    - div_curr_year : dividends paid in current fiscal year so far

Safe to run multiple times — checks if each column already exists first.

Usage:
    python scripts/migrate_add_price_extras.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection


NEW_COLUMNS = [
    ("todays_range",   "TEXT"),
    ("week52_range",   "TEXT"),
    ("div_prev_year",  "REAL"),
    ("div_curr_year",  "REAL"),
]


def get_existing_columns(conn, table: str) -> set:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def main() -> None:
    print("=" * 60)
    print("JSEdge — Migration: add price-extras columns to prices_daily")
    print("=" * 60)

    conn = get_connection()
    try:
        existing = get_existing_columns(conn, "prices_daily")
        print(f"Existing columns in 'prices_daily': {len(existing)}")

        added = 0
        skipped = 0
        for col_name, col_type in NEW_COLUMNS:
            if col_name in existing:
                print(f"  ⏭  Skipping '{col_name}' — already exists.")
                skipped += 1
            else:
                conn.execute(f"ALTER TABLE prices_daily ADD COLUMN {col_name} {col_type}")
                print(f"  ✅ Added '{col_name}' ({col_type}).")
                added += 1

        conn.commit()
    finally:
        conn.close()

    print()
    print(f"Migration complete: {added} added, {skipped} skipped.")
    print("=" * 60)


if __name__ == "__main__":
    main()