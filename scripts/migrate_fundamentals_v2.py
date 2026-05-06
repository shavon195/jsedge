"""
JSEdge — Migration: upgrade `fundamentals` table for horizon-aware ranking.

Changes:
    1. Rename column `report_date` -> `period_end_date`
    2. Expand `period_type` CHECK to allow 'half_year' and 'ttm'
    3. Add columns: total_assets, operating_income,
                    operating_cash_flow, free_cash_flow

Why this migration is bigger than usual:
    SQLite can ALTER TABLE to ADD columns easily, but RENAME column
    requires SQLite 3.25+ and changing a CHECK constraint requires
    rebuilding the table.

    The safe pattern is:
        a. Create a new table with the desired schema
        b. Copy data from old table to new
        c. Drop the old table
        d. Rename the new table to the original name

    The `fundamentals` table is currently empty, so step (b) copies
    zero rows. But the script handles non-empty tables gracefully too.

Safe to run multiple times — checks if migration already happened first.

Usage:
    python scripts/migrate_fundamentals_v2.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection


def get_columns(conn, table: str) -> set:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def already_migrated(conn) -> bool:
    """Check if the new schema is already in place."""
    cols = get_columns(conn, "fundamentals")
    required = {"period_end_date", "total_assets", "operating_income",
                "operating_cash_flow", "free_cash_flow"}
    return required.issubset(cols)


def main() -> None:
    print("=" * 60)
    print("JSEdge — Migration: fundamentals v2")
    print("=" * 60)

    conn = get_connection()
    try:
        if already_migrated(conn):
            print("✅ Migration already applied. Nothing to do.")
            return

        print("Building new fundamentals table...")

        # Step 1: rename old table out of the way.
        conn.execute("ALTER TABLE fundamentals RENAME TO fundamentals_old")

        # Step 2: create the new table with the desired schema.
        conn.execute("""
            CREATE TABLE fundamentals (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_id            INTEGER NOT NULL,
                period_end_date     TEXT    NOT NULL,
                period_type         TEXT    NOT NULL CHECK (period_type IN ('quarterly', 'half_year', 'annual', 'ttm')),
                eps                 REAL,
                pe_ratio            REAL,
                pb_ratio            REAL,
                dividend_yield      REAL,
                total_debt          REAL,
                total_equity        REAL,
                total_assets        REAL,
                net_income          REAL,
                operating_income    REAL,
                operating_cash_flow REAL,
                free_cash_flow      REAL,
                revenue             REAL,
                shares_outstanding  REAL,
                source              TEXT    NOT NULL CHECK (source IN ('scraped', 'manual')),
                notes               TEXT,
                created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at          TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (stock_id) REFERENCES stocks(id) ON DELETE CASCADE,
                UNIQUE (stock_id, period_end_date, period_type)
            )
        """)

        # Step 3: copy any existing rows from the old table.
        # Old `report_date` becomes new `period_end_date`.
        # New columns (total_assets, operating_income, OCF, FCF) start NULL.
        old_count = conn.execute(
            "SELECT COUNT(*) FROM fundamentals_old"
        ).fetchone()[0]

        if old_count > 0:
            print(f"  Copying {old_count} existing rows...")
            conn.execute("""
                INSERT INTO fundamentals (
                    id, stock_id, period_end_date, period_type,
                    eps, pe_ratio, pb_ratio, dividend_yield,
                    total_debt, total_equity, net_income,
                    revenue, shares_outstanding,
                    source, notes, created_at, updated_at
                )
                SELECT
                    id, stock_id, report_date, period_type,
                    eps, pe_ratio, pb_ratio, dividend_yield,
                    total_debt, total_equity, net_income,
                    revenue, shares_outstanding,
                    source, notes, created_at, updated_at
                FROM fundamentals_old
            """)
        else:
            print("  No existing rows to copy.")

        # Step 4: drop the old table.
        conn.execute("DROP TABLE fundamentals_old")

        # Step 5: recreate the index.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fundamentals_stock "
            "ON fundamentals(stock_id)"
        )

        conn.commit()
        print("✅ Migration complete.")

    finally:
        conn.close()

    # Show the final column list for verification.
    conn = get_connection()
    try:
        print("\nFinal columns:")
        for row in conn.execute("PRAGMA table_info(fundamentals)"):
            print(f"  {row['name']:<22} {row['type']}")
    finally:
        conn.close()

    print("=" * 60)


if __name__ == "__main__":
    main()