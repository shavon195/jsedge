"""Debug script - see what the FULL Observer pipeline produces.

This calls scrape_observer_business(), which runs:
    fetch -> parse -> enrich snippets -> relevance filter
and prints the relevant articles + why they were kept.
"""

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from app.news import scrape_observer_business


def main() -> None:
    articles = scrape_observer_business()

    print()
    print("=" * 70)
    print(f"FINAL RESULT: {len(articles)} relevant articles")
    print("=" * 70)

    for i, art in enumerate(articles, start=1):
        print(f"\n[{i}] HEADLINE: {art['headline']!r}")
        print(f"    URL:      {art['url']}")
        snip = art.get("snippet") or ""
        if snip:
            display = snip if len(snip) <= 200 else snip[:200] + "..."
            print(f"    SNIPPET:  {display!r}")
        else:
            print(f"    SNIPPET:  (none)")
        print(f"    DATE:     {art.get('published_at')}")

        direct = art.get("matched_stocks") or []
        themes = art.get("matched_themes") or []
        macros = art.get("matched_macros") or []
        if direct:
            print(f"       Direct: {', '.join(direct)}")
        for theme in themes:
            stocks_str = ", ".join(theme["affected_stocks"]) or "(no new stocks)"
            print(f"       Theme '{theme['name']}' -> {stocks_str}")
        if macros:
            print(f"       Macros: {', '.join(macros)}")


if __name__ == "__main__":
    main()