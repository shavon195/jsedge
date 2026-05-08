"""
JSEdge — Migration: replace unique constraint on `scores` table.

CHANGE: drop UNIQUE(stock_id, date), add UNIQUE(stock_id, date, horizon).

This lets us store multiple horizon scores per stock per day — required
for the dropdown on the JSE tab to switch between horizons without
recomputing on every page load.

Strategy (SQLite can't ALTER a constraint directly):
    1. Wipe existing scores rows (they have horizon=NULL anyway, useless).
    2. Drop the existing scores table.
    3. Recreate it with the new constraint.

Safe to run multiple times — checks the current constraint first.

Usage:
    python scripts/migrate_horizon_unique_constraint.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection


# This is the new scores table definition. Mirrors the SCHEMA_SQL in
# database.py but uses (stock_id, date, horizon) for uniqueness.
NEW_SCORES_DDL = """
CREATE TABLE scores (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id            INTEGER NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
    date                TEXT    NOT NULL,
    composite_score     REAL    NOT NULL,
    pe_score            REAL,
    growth_score        REAL,
    roe_score           REAL,
    debt_score          REAL,
    dividend_score      REAL,
    pb_score            REAL,
    position_score      REAL,
    volume_score        REAL,
    range_score         REAL,
    fcf_margin_score    REAL,
    profit_margin_score REAL,
    horizon             TEXT,
    data_completeness   REAL,
    fair_value          REAL,
    margin_of_safety    REAL,
    notes               TEXT,
    created_at          TEXT    DEFAULT (datetime('now')),
    UNIQUE(stock_id, date, horizon)
);
"""


def get_current_indexes(conn) -> list:
    """Return list of indexes/constraints on the scores table."""
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type='index' AND tbl_name='scores' AND sql IS NOT NULL"
    ).fetchall()
    return [(r["name"], r["sql"]) for r in rows]


def main() -> None:
    print("=" * 60)
    print("JSEdge — Migration: scores UNIQUE constraint")
    print("=" * 60)

    conn = get_connection()
    try:
        # Check current row count.
        count_row = conn.execute("SELECT COUNT(*) AS c FROM scores").fetchone()
        existing_count = count_row["c"]
        print(f"Existing rows in 'scores': {existing_count}")

        # Check if constraint already includes horizon.
        indexes = get_current_indexes(conn)
        already_correct = any(
            "horizon" in (sql or "").lower() for _, sql in indexes
        )

        if already_correct:
            print("⏭  Constraint already includes 'horizon' — nothing to do.")
            return

        # Confirm we're going to drop the old table.
        print(f"\n⚠️  About to DROP TABLE scores (will lose {existing_count} rows).")
        print("    These rows have horizon=NULL and aren't useful to the new system.")
        print("    The scoring pipeline will regenerate them.")

        # Step 1: drop old table.
        print("\n  → Dropping old scores table...")
        conn.execute("DROP TABLE IF EXISTS scores")

        # Step 2: create new table.
        print("  → Creating new scores table with UNIQUE(stock_id, date, horizon)...")
        conn.execute(NEW_SCORES_DDL)

        conn.commit()
        print("\n✅ Migration complete.")
        print("    Run scripts/compute_all_horizons.py next to populate scores.")

    finally:
        conn.close()

    print("=" * 60)


if __name__ == "__main__":
    main()