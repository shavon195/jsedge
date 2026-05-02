"""
JSEdge — Migration: add technical-score columns to the `scores` table.

Adds these columns to support technical (price-based) ranking:
    - position_score    : 52-week position score (0-100)
    - volume_score      : liquidity score (0-100)
    - range_score       : intraday range stability score (0-100)
    - data_completeness : ratio of signals with valid data (0.0-1.0)

Safe to run multiple times — checks if each column already exists first.

Usage:
    python scripts/migrate_add_technical_scores.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection


NEW_COLUMNS = [
    ("position_score",    "REAL"),
    ("volume_score",      "REAL"),
    ("range_score",       "REAL"),
    ("data_completeness", "REAL"),
]


def get_existing_columns(conn, table: str) -> set:
    """Return the set of column names currently in the table."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def main() -> None:
    print("=" * 60)
    print("JSEdge — Migration: add technical-score columns")
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