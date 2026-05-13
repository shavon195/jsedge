"""Debug script — see what the Gleaner scraper actually parsed."""

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from app.news import (
    fetch_business_page,
    parse_article_cards,
    article_relevance,
)


def main() -> None:
    html = fetch_business_page()
    if html is None:
        print("❌ Fetch failed.")
        return

    print(f"\n✅ Fetched {len(html)} bytes of HTML\n")

    articles = parse_article_cards(html)

    print(f"📰 Parser extracted {len(articles)} article cards.\n")
    print("=" * 70)

    for i, art in enumerate(articles, start=1):
        print(f"\n[{i}] HEADLINE: {art['headline']!r}")
        print(f"    URL:      {art['url']}")
        snip = art.get("snippet")
        if snip:
            display = snip if len(snip) <= 150 else snip[:150] + "..."
            print(f"    SNIPPET:  {display!r}")
        else:
            print(f"    SNIPPET:  (none)")

        # Show why each article was filtered.
        rel = article_relevance(art)
        if rel["relevant"]:
            print(f"    ✅ KEPT")
            if rel["matched_stocks"]:
                print(f"       Direct: {', '.join(rel['matched_stocks'])}")
            for theme in rel["matched_themes"]:
                stocks_str = ", ".join(theme["affected_stocks"]) or "(no new stocks)"
                kw_str = ", ".join(theme["matched_keywords"][:2])
                if len(theme["matched_keywords"]) > 2:
                    kw_str += f" (+{len(theme['matched_keywords']) - 2} more)"
                print(f"       Theme '{theme['name']}' → {stocks_str}  [matched: {kw_str}]")
            if rel["matched_macros"]:
                print(f"       Macros: {', '.join(rel['matched_macros'])}")
        else:
            print(f"    ❌ SKIPPED — {rel['reason']}")

if __name__ == "__main__":
    main()