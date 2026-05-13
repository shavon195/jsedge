"""
JSEdge — Migration: add news_articles + news_stock_links tables.

Adds two new tables to support the News tab:

    news_articles    — one row per scraped article. Stores headline,
                       URL, source, publish date, raw snippet, and
                       (eventually) AI summary.

    news_stock_links — many-to-many between articles and stocks.
                       One row per (article, stock) association.
                       Tracks whether the link was auto-tagged or
                       manually overridden.

Safe to run multiple times — uses CREATE TABLE IF NOT EXISTS.

Usage:
    python scripts/migrate_add_news_tables.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection


NEWS_ARTICLES_DDL = """
CREATE TABLE IF NOT EXISTS news_articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT    NOT NULL,        -- 'gleaner', 'observer', 'jse_filings'
    url             TEXT    NOT NULL UNIQUE, -- canonical article URL (dedupe key)
    headline        TEXT    NOT NULL,
    snippet         TEXT,                    -- short excerpt from the article
    full_text       TEXT,                    -- full body if we extracted it (may be null)
    published_at    TEXT,                    -- ISO date or datetime from the source
    scraped_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    ai_summary      TEXT,                    -- AI-generated summary (filled in later)
    ai_summary_at   TEXT,                    -- when the summary was generated
    notes           TEXT                     -- free-form notes
);
"""

NEWS_STOCK_LINKS_DDL = """
CREATE TABLE IF NOT EXISTS news_stock_links (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER NOT NULL REFERENCES news_articles(id) ON DELETE CASCADE,
    stock_id        INTEGER NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
    source          TEXT    NOT NULL DEFAULT 'auto',  -- 'auto' or 'manual'
    confidence      REAL,                              -- 0.0-1.0 for auto-tags (keyword match score)
    matched_keyword TEXT,                              -- which keyword triggered the auto-tag
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(article_id, stock_id)
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_news_articles_source ON news_articles(source)",
    "CREATE INDEX IF NOT EXISTS idx_news_articles_published ON news_articles(published_at)",
    "CREATE INDEX IF NOT EXISTS idx_news_stock_links_stock ON news_stock_links(stock_id)",
    "CREATE INDEX IF NOT EXISTS idx_news_stock_links_article ON news_stock_links(article_id)",
]


def main() -> None:
    print("=" * 60)
    print("JSEdge — Migration: add news tables")
    print("=" * 60)

    conn = get_connection()
    try:
        # Check what exists already.
        existing_tables = {
            r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        print(f"Existing tables: {len(existing_tables)}")

        # Create tables.
        if "news_articles" in existing_tables:
            print("  ⏭  news_articles — already exists")
        else:
            conn.execute(NEWS_ARTICLES_DDL)
            print("  ✅ Created news_articles")

        if "news_stock_links" in existing_tables:
            print("  ⏭  news_stock_links — already exists")
        else:
            conn.execute(NEWS_STOCK_LINKS_DDL)
            print("  ✅ Created news_stock_links")

        # Create indexes (idempotent).
        print("\n  Creating indexes...")
        for ddl in INDEXES:
            conn.execute(ddl)
        print(f"  ✅ {len(INDEXES)} indexes verified.")

        conn.commit()

    finally:
        conn.close()

    print("\n✅ Migration complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()