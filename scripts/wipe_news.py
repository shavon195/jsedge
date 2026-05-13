"""
JSEdge — Wipe news tables.

Deletes ALL rows from news_articles and news_stock_links. Used to get
a clean slate before re-running the news scraper for verification.

Asks for confirmation before wiping. Run from repo root:

    python scripts/wipe_news.py
"""

import sys
from pathlib import Path

# Make `app` importable when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_connection


def main() -> None:
    conn = get_connection()
    try:
        # Show current counts so the user knows what they're about to nuke.
        articles_count = conn.execute(
            "SELECT COUNT(*) AS n FROM news_articles"
        ).fetchone()["n"]
        links_count = conn.execute(
            "SELECT COUNT(*) AS n FROM news_stock_links"
        ).fetchone()["n"]

        print(f"Current state:")
        print(f"  news_articles:     {articles_count} rows")
        print(f"  news_stock_links:  {links_count} rows")
        print()

        if articles_count == 0 and links_count == 0:
            print("Both tables already empty. Nothing to wipe.")
            return

        answer = input("Wipe BOTH tables completely? (y/n): ").strip().lower()
        if answer != "y":
            print("Aborted. No changes made.")
            return

        # Delete links first to respect FK constraints (links -> articles).
        conn.execute("DELETE FROM news_stock_links")
        conn.execute("DELETE FROM news_articles")
        conn.commit()

        print()
        print("Wiped.")
        print(f"  news_articles:     0 rows")
        print(f"  news_stock_links:  0 rows")
    finally:
        conn.close()


if __name__ == "__main__":
    main()