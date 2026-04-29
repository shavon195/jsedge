"""
JSEdge — JSE website scraper.

Fetches daily trade quotes from jamstockex.com and stores them in
the database. Phase 1: just fetching pages and proving we can read them.
"""

import logging
from datetime import date
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = "https://www.jamstockex.com/trading/trade-quotes/"

# Market IDs as observed on jamstockex.com:
#   31 = Main Market
#   22 = Junior Market
# We'll add more (USD, etc.) if we discover them.
MARKETS = {
    "main":   31,
    "junior": 22,
}

# Pretend to be a normal browser. Some sites block requests with no user-agent
# or generic Python defaults. Being polite about identifying ourselves is good
# scraping etiquette and reduces the chance of getting blocked.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Don't wait forever for a slow response.
REQUEST_TIMEOUT_SECONDS = 30

# Set up logging so we can see what's happening when the scraper runs.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Page fetcher
# ---------------------------------------------------------------------------
def fetch_trade_quotes_page(market: str, target_date: Optional[date] = None) -> str:
    """
    Download the HTML of the JSE trade quotes page for one market on one date.

    Args:
        market: 'main' or 'junior'.
        target_date: a Python date. Defaults to today if not given.

    Returns:
        The full HTML of the page as a string.

    Raises:
        ValueError: if `market` isn't recognized.
        requests.HTTPError: if the server returns a non-200 status.
    """
    if market not in MARKETS:
        raise ValueError(
            f"Unknown market '{market}'. Valid choices: {list(MARKETS.keys())}"
        )

    if target_date is None:
        target_date = date.today()

    params = {
        "market": MARKETS[market],
        "date":   target_date.isoformat(),  # 'YYYY-MM-DD'
    }

    log.info(
        "Fetching %s market for %s ...",
        market, target_date.isoformat()
    )

    response = requests.get(
        BASE_URL,
        params=params,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()  # blow up if the server says no

    log.info(
        "Received %d bytes (status %d).",
        len(response.text), response.status_code
    )

    return response.text


# ---------------------------------------------------------------------------
# Manual test entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Run this file directly to test that fetching works:
    #     python app/scraper.py
    html = fetch_trade_quotes_page("main")

    # Print first 500 characters so we can eyeball the HTML.
    print("\n--- First 500 chars of the response ---")
    print(html[:500])
    print("--- end ---")

    # Quick sanity check: is the symbol "138SL" in there?
    if "138SL" in html:
        print("\n✅ Found '138SL' in HTML — scraping target confirmed!")
    else:
        print("\n⚠️  Did NOT find '138SL'. Either the market is empty today")
        print("   or the page structure changed. Investigate.")