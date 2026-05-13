"""
JSEdge — Full news scraping pipeline.

Fetches latest articles from Jamaica Gleaner, filters for relevance,
and saves them to the database.

Usage:
    python scripts/scrape_news.py
"""

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)

from app.news import (
    scrape_gleaner_business,
    scrape_observer_business,
    save_articles_to_db,
)

def main() -> None:
    print("=" * 70)
    print("JSEdge — News scrape pipeline")
    print("=" * 70)

    # Step 1: scrape + filter from each source.
    print("\n--- Source: Jamaica Gleaner ---")
    gleaner_articles = scrape_gleaner_business()

    print("\n--- Source: Jamaica Observer ---")
    observer_articles = scrape_observer_business()

    articles = gleaner_articles + observer_articles

    if not articles:
        print("\n⚠️  No relevant articles found this run.")
        return

    print(f"\n📰 {len(articles)} relevant articles total to save "
          f"({len(gleaner_articles)} Gleaner + {len(observer_articles)} Observer):")
    for a in articles:
        direct = ", ".join(a.get("matched_stocks", [])) or "—"
        themes = ", ".join(t["name"] for t in a.get("matched_themes", [])) or "—"
        source = a.get("source", "?")
        print(f"   • [{source}] {a['headline'][:60]}")
        print(f"     direct={direct} | themes={themes}")

    # Step 2: save to DB.
    print("\n💾 Saving to database...")
    result = save_articles_to_db(articles)
    print()
    print("=" * 70)
    print("✅ Results:")
    print(f"   Articles inserted:     {result['articles_inserted']}")
    print(f"   Articles updated:      {result['articles_updated']}")
    print(f"   Auto links created:    {result['links_auto']}")
    print(f"   Thematic links created: {result['links_thematic']}")
    print(f"   Manual links preserved: {result['links_preserved_manual']}")
    print("=" * 70)


if __name__ == "__main__":
    main()