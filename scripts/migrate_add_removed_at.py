"""
JSEdge - Migration: add removed_at column to news_stock_links.

This supports soft-delete of news article tags. When a user manually
removes an auto/thematic link via the news UI, we set removed_at = now()
instead of deleting the row. The re-scrape pipeline then skips re-creating
any link where a soft-deleted row already exists for the same
(article_id, stock_id) pair.

Safe to run multiple times: checks if the column already exists first.

Usage:
    python scripts/migrate_add_removed_at.py
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
        if column_exists(conn, "news_stock_links", "removed_at"):
            print("Column 'removed_at' already exists on news_stock_links.")
            print("Nothing to do.")
            return

        print("Adding column 'removed_at' to news_stock_links...")
        conn.execute(
            "ALTER TABLE news_stock_links ADD COLUMN removed_at TEXT"
        )
        conn.commit()

        # Verify it took.
        if column_exists(conn, "news_stock_links", "removed_at"):
            print("Column added successfully.")
        else:
            print("ERROR: column did not appear after ALTER TABLE.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()