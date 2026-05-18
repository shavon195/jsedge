"""
JSEdge — Migration: fundamentals v3 (drop derived ratio columns).

Changes:
    1. DROP columns: pe_ratio, pb_ratio, dividend_yield
    2. ADD column:   dividend_per_share REAL

Rationale:
    P/E, P/B, and dividend yield are *derived* from price + fundamentals.
    Storing them as snapshots means they go stale the moment the price
    moves. The ranking engine never reads these columns anyway, but the
    view template displays the stale values, and the form takes them as
    input — all wasted effort.

    After this migration:
        - P/E             = prices_daily.close_price / fundamentals.eps
        - P/B             = (close_price * shares_outstanding) / total_equity
        - dividend yield  = fundamentals.dividend_per_share / close_price

    All computed live wherever they're displayed. No stale data.

Why dividend_per_share is the only new column:
    Book value per share is already derivable (total_equity / shares_outstanding),
    so we don't store it. But dividend-per-share isn't currently anywhere in
    fundamentals — it has to be a new input. NULL for existing 15 rows; you
    backfill manually from their source filings.

Migration pattern (same as v2):
    a. Rename old table -> fundamentals_old
    b. Create new table with desired schema
    c. INSERT ... SELECT to copy all 15 rows, omitting the 3 dropped columns
    d. DROP fundamentals_old
    e. Recreate index

Safe to run multiple times — checks if migration already applied.

Usage:
    python scripts/migrate_fundamentals_v3.py
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
    """v3 is done when dividend_per_share exists AND the three doomed cols are gone."""
    cols = get_columns(conn, "fundamentals")
    doomed_gone   = not any(c in cols for c in ("pe_ratio", "pb_ratio", "dividend_yield"))
    new_col_added = "dividend_per_share" in cols
    return doomed_gone and new_col_added


def main() -> None:
    print("=" * 60)
    print("JSEdge — Migration: fundamentals v3")
    print("  DROP: pe_ratio, pb_ratio, dividend_yield")
    print("  ADD:  dividend_per_share")
    print("=" * 60)

    conn = get_connection()
    try:
        if already_migrated(conn):
            print("✅ Migration already applied. Nothing to do.")
            return

        # Show what we're about to migrate.
        old_count = conn.execute("SELECT COUNT(*) FROM fundamentals").fetchone()[0]
        print(f"Will migrate {old_count} existing rows.")
        print()

        # Step 1: rename old table.
        print("Step 1/5: Renaming fundamentals -> fundamentals_old...")
        conn.execute("ALTER TABLE fundamentals RENAME TO fundamentals_old")

        # Step 2: create new table with v3 schema.
        print("Step 2/5: Creating new fundamentals table...")
        conn.execute("""
            CREATE TABLE fundamentals (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_id            INTEGER NOT NULL,
                period_end_date     TEXT    NOT NULL,
                period_type         TEXT    NOT NULL CHECK (period_type IN ('quarterly', 'half_year', 'annual', 'ttm')),
                eps                 REAL,
                dividend_per_share  REAL,
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

        # Step 3: copy data, omitting the three dropped columns.
        # dividend_per_share is NOT in the SELECT — it stays NULL for all rows.
        print(f"Step 3/5: Copying {old_count} rows (dividend_per_share will be NULL)...")
        conn.execute("""
            INSERT INTO fundamentals (
                id, stock_id, period_end_date, period_type,
                eps,
                total_debt, total_equity, total_assets,
                net_income, operating_income,
                operating_cash_flow, free_cash_flow,
                revenue, shares_outstanding,
                source, notes, created_at, updated_at
            )
            SELECT
                id, stock_id, period_end_date, period_type,
                eps,
                total_debt, total_equity, total_assets,
                net_income, operating_income,
                operating_cash_flow, free_cash_flow,
                revenue, shares_outstanding,
                source, notes, created_at, updated_at
            FROM fundamentals_old
        """)

        # Verify row count matches before dropping the old table.
        new_count = conn.execute("SELECT COUNT(*) FROM fundamentals").fetchone()[0]
        if new_count != old_count:
            raise RuntimeError(
                f"Row count mismatch! old={old_count}, new={new_count}. "
                "Aborting before DROP."
            )
        print(f"  ✓ Verified: {new_count} rows copied.")

        # Step 4: drop the old table.
        print("Step 4/5: Dropping fundamentals_old...")
        conn.execute("DROP TABLE fundamentals_old")

        # Step 5: recreate the index.
        print("Step 5/5: Recreating index...")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fundamentals_stock "
            "ON fundamentals(stock_id)"
        )

        conn.commit()
        print()
        print("✅ Migration complete.")

    finally:
        conn.close()

    # Show the final column list for verification.
    conn = get_connection()
    try:
        print()
        print("Final columns:")
        for row in conn.execute("PRAGMA table_info(fundamentals)"):
            print(f"  {row['name']:<22} {row['type']}")
        print()
        final_count = conn.execute("SELECT COUNT(*) FROM fundamentals").fetchone()[0]
        print(f"Final row count: {final_count}")
    finally:
        conn.close()

    print("=" * 60)


if __name__ == "__main__":
    main()