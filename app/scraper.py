"""
JSEdge — JSE website scraper.

Fetches daily trade quotes from jamstockex.com and stores them in
the database. Phase 1: just fetching pages and proving we can read them.
"""

import logging
from datetime import date
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

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
# Local sample loader (for offline parser development)
# ---------------------------------------------------------------------------
def load_sample_html(market: str, sample_date: str = "2026-04-28") -> str:
    """
    Read a saved HTML sample file from disk.

    Useful while developing the parser — avoids hammering jamstockex.com
    with every test run.

    Args:
        market: 'main' or 'junior'.
        sample_date: ISO date string. Defaults to our known-good sample.

    Returns:
        The HTML content as a string.

    Raises:
        FileNotFoundError: if the sample file doesn't exist.
    """
    samples_dir = Path(__file__).parent.parent / "data" / "samples"
    sample_file = samples_dir / f"{market}_{sample_date}.html"

    if not sample_file.exists():
        raise FileNotFoundError(
            f"Sample file not found: {sample_file}\n"
            f"Run `python scripts/save_sample_html.py` first to create it."
        )

    return sample_file.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Parser — find the stocks table
# ---------------------------------------------------------------------------
def find_stocks_table(html: str):
    """
    Locate the table containing main/junior market stock rows.

    The trade-quotes page contains multiple tables (Indices, Main Market,
    Preference Shares, etc.). We identify the stocks table by checking
    each table's column count — the stocks table has 12 columns matching
    the known JSE schema.

    Args:
        html: full HTML of the trade-quotes page.

    Returns:
        The matching <table> Tag from BeautifulSoup, or None if not found.
    """
    EXPECTED_COLUMNS = 12  # arrow + symbol + 10 data columns

    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")

    log.info("Found %d tables on the page.", len(tables))

    for i, table in enumerate(tables):
        header_row = table.find("tr")
        if header_row is None:
            continue
        col_count = len(header_row.find_all(["th", "td"]))
        log.info("  Table %d has %d columns.", i, col_count)

        if col_count == EXPECTED_COLUMNS:
            return table

    return None

# ---------------------------------------------------------------------------
# Parser — extract data from a single stock row
# ---------------------------------------------------------------------------
def parse_stock_row(row) -> dict:
    """
    Extract data from one <tr> element of the stocks table.

    The expected column order (12 cells) is:
        0:  arrow image (up/down/flat) — skipped
        1:  symbol (inside an <a> tag, with full company name in title=)
        2:  last traded price ($)
        3:  closing price ($)
        4:  price change ($)
        5:  closing bid ($)
        6:  closing ask ($)
        7:  volume
        8:  today's range ($)
        9:  52-week range ($)
        10: total prev year div ($)
        11: total current year div ($)

    Args:
        row: a BeautifulSoup <tr> Tag.

    Returns:
        Dictionary of cleaned values, with None for empty/missing fields.
    """
    cells = row.find_all("td")
    if len(cells) < 12:
        return {}  # not a valid stock row, skip it

    # --- helper: collapse all whitespace (newlines, tabs, multi-spaces) into single spaces ---
    def clean_text(text: str) -> str:
        return " ".join(text.split()).strip()


    # --- symbol + name (cell 1) ---
    symbol_link = cells[1].find("a")
    symbol = symbol_link.get_text(strip=True) if symbol_link else None
    name   = symbol_link.get("title") if symbol_link else None

    # --- helper: convert "1,234.56" or "" to float, or None if blank/dash ---
    def to_float(text: str):
        text = text.strip().replace(",", "")
        if text in ("", "-", "—"):
            return None
        try:
            return float(text)
        except ValueError:
            return None

    # --- helper: convert "1,234,567" volume to int, or None ---
    def to_int(text: str):
        text = text.strip().replace(",", "")
        if text in ("", "-", "—"):
            return None
        try:
            return int(text)
        except ValueError:
            return None

    return {
        "symbol":          symbol,
        "name":            name,
        "last_price":      to_float(cells[2].get_text()),
        "closing_price":   to_float(cells[3].get_text()),
        "price_change":    to_float(cells[4].get_text()),
        "closing_bid":     to_float(cells[5].get_text()),
        "closing_ask":     to_float(cells[6].get_text()),
        "volume":          to_int(cells[7].get_text()),
        "todays_range":    clean_text(cells[8].get_text()) or None,
        "week52_range":    clean_text(cells[9].get_text()) or None,
        "div_prev_year":   to_float(cells[10].get_text()),
        "div_curr_year":   to_float(cells[11].get_text()),
    }

# ---------------------------------------------------------------------------
# Parser — extract all rows from the stocks table
# ---------------------------------------------------------------------------
def parse_all_stocks(html: str) -> list[dict]:
    """
    Parse every stock row from the trade-quotes HTML.

    Wires together find_stocks_table() and parse_stock_row().

    Args:
        html: full HTML of a trade-quotes page.

    Returns:
        List of dictionaries, one per stock. Empty list if no table found.
    """
    table = find_stocks_table(html)
    if table is None:
        log.warning("No stocks table found on the page.")
        return []

    body = table.find("tbody")
    if body is None:
        log.warning("Stocks table has no <tbody>.")
        return []

    stocks = []
    for row in body.find_all("tr"):
        parsed = parse_stock_row(row)
        if parsed:  # skip empty/invalid rows
            stocks.append(parsed)

    log.info("Parsed %d stocks from the page.", len(stocks))
    return stocks

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