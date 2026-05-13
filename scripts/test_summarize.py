"""
JSEdge - Test script for the Gemini summarizer.

Picks the most recent article from the DB, runs the summarizer on it,
and prints the result. Use this to verify the API key works and the
prompt produces sensible output BEFORE wiring up the web UI.

Usage:
    python scripts/test_summarize.py
    python scripts/test_summarize.py 22       # specify article id
"""

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from app.database import get_connection
from app.news.summarizer import summarize_article


def main() -> None:
    # Optional article_id arg; default to the most recent article.
    article_id: int
    if len(sys.argv) >= 2:
        try:
            article_id = int(sys.argv[1])
        except ValueError:
            print(f"Invalid article id: {sys.argv[1]!r}")
            return
    else:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT id, headline FROM news_articles "
                "ORDER BY COALESCE(published_at, scraped_at) DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            print("No articles in DB. Run scripts/scrape_news.py first.")
            return
        article_id = row["id"]

    # Show what we're about to summarize.
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, source, headline, snippet FROM news_articles WHERE id = ?",
            (article_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        print(f"Article {article_id} not found.")
        return

    print("=" * 70)
    print(f"Article #{row['id']} [{row['source']}]")
    print(f"Headline: {row['headline']}")
    snippet = row["snippet"] or "(no snippet)"
    print(f"Snippet:  {snippet[:200]}{'...' if len(snippet) > 200 else ''}")
    print("=" * 70)
    print()
    print("Calling Gemini...")
    print()

    result = summarize_article(article_id)
    if not result["ok"]:
        print(f"FAILED: {result['error']}")
        return

    print("SUMMARY:")
    print(result["summary"])


if __name__ == "__main__":
    main()