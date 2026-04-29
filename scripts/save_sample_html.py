"""
JSEdge — Save sample HTML pages from jamstockex.com.

Hits the live site once per market and saves the raw HTML response to
disk. Subsequent parser development can read these files instead of
hammering the real site, which is faster and more polite.

Usage:
    python scripts/save_sample_html.py
"""

import sys
from datetime import date
from pathlib import Path

# Allow imports from the project root (so we can use app/scraper.py).
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.scraper import fetch_trade_quotes_page

# We pick a specific date that we know had full trading activity.
# April 28, 2026 was a full trading day — confirmed by earlier tests.
SAMPLE_DATE = date(2026, 4, 28)

# Where to save the files.
OUTPUT_DIR = PROJECT_ROOT / "data" / "samples"


def save_market(market: str) -> None:
    html = fetch_trade_quotes_page(market, SAMPLE_DATE)
    out_path = OUTPUT_DIR / f"{market}_{SAMPLE_DATE.isoformat()}.html"
    out_path.write_text(html, encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"  ✅ Saved {out_path.relative_to(PROJECT_ROOT)} ({size_kb:.1f} KB)")


def main() -> None:
    print("=" * 60)
    print(f"JSEdge — Saving sample HTML for {SAMPLE_DATE.isoformat()}")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for market in ["main", "junior"]:
        save_market(market)

    print()
    print("Sample files ready. Use these for offline parser development.")
    print("=" * 60)


if __name__ == "__main__":
    main()