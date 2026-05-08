"""
JSEdge — Migration: add horizon-aware columns to the `scores` table.

Adds 3 new columns to support horizon-aware ranking:
    - fcf_margin_score    : score for Free Cash Flow margin
    - profit_margin_score : score for net profit margin
    - horizon             : which horizon this score was computed for
                            (6_months / 1_year / 2_years / 5_years / 10_years)

Safe to run multiple times — checks if each column already exists first.

Usage:
    python scripts/migrate_add_horizon_scores.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection


NEW_COLUMNS = [
    ("fcf_margin_score",    "REAL"),
    ("profit_margin_score", "REAL"),
    ("horizon",             "TEXT"),
]


def get_existing_columns(conn, table: str) -> set:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def main() -> None:
    print("=" * 60)
    print("JSEdge — Migration: add horizon-aware score columns")
    print("=" * 60)

    conn = get_connection()
    try:
        existing = get_existing_columns(conn, "scores")
        print(f"Existing columns in 'scores': {len(existing)}")

        added = 0
        skipped = 0
        for col_name, col_type in NEW_COLUMNS:
            if col_name in existing:
                print(f"  ⏭  Skipping '{col_name}' — already exists.")
                skipped += 1
            else:
                conn.execute(f"ALTER TABLE scores ADD COLUMN {col_name} {col_type}")
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