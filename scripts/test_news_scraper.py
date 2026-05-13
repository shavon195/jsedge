"""Quick test of the Gleaner news scraper."""

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Verbose logging so we see what the scraper is doing.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
)

from app.news_scraper import scrape_gleaner_business


def main() -> None:
    print("=" * 70)
    print("JSEdge — Test scrape of Jamaica Gleaner business section")
    print("=" * 70)

    articles = scrape_gleaner_business()

    print()
    print("=" * 70)
    print(f"RESULTS: {len(articles)} relevant articles kept")
    print("=" * 70)

    if not articles:
        print("\n⚠️  No relevant articles. Possible reasons:")
        print("   - The page has only international news today (rare)")
        print("   - The Gleaner HTML changed and our parser missed cards")
        print("   - Fetch failed (check log above for errors)")
        return

    for i, a in enumerate(articles, start=1):
        print(f"\n[{i}] {a['headline']}")
        print(f"    URL:     {a['url']}")
        if a.get("snippet"):
            snippet = a["snippet"]
            if len(snippet) > 120:
                snippet = snippet[:120] + "..."
            print(f"    Snippet: {snippet}")
        if a.get("published_at"):
            print(f"    Date:    {a['published_at']}")
        if a.get("matched_stocks"):
            print(f"    Stocks:  {', '.join(a['matched_stocks'])}")
        if a.get("matched_macros"):
            print(f"    Macros:  {', '.join(a['matched_macros'])}")


if __name__ == "__main__":
    main()