"""
JSEdge - Fetch instrument codes from the JSE Price History page.

The JSE Price History page (https://www.jamstockex.com/trading/price-history/)
includes a <select> dropdown listing every instrument with its
numeric code. We scrape that dropdown to build a symbol -> code
mapping, then save the codes back to our stocks table.

This is a one-shot script - run it once after the migration. Re-run
any time JSE adds new listings to pick them up.

Only saves codes for instruments in Main Market or Junior Market
that match an existing symbol in our stocks table. Skips:
    - USD Market / Private Market / Bond instruments
    - PREFERENCE shares (different security type)
    - Symbols we don't have in our DB yet

Usage:
    python scripts/fetch_instrument_codes.py
"""

import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection

URL = "https://www.jamstockex.com/trading/price-history/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Regex to parse "COMPANY NAME (SYMBOL:Market Name)" from option text.
# Captures the symbol and market name groups.
LABEL_PATTERN = re.compile(
    r"\(([A-Z0-9]+):\s*(Main Market|Junior Market|USD Market|Private Market)\)\s*$"
)

# Markets we want to keep.
ALLOWED_MARKETS = {"Main Market", "Junior Market"}


def fetch_page() -> str:
    """Download the price-history page HTML."""
    print(f"Fetching {URL}...")
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    print(f"  received {len(resp.text):,} bytes (status {resp.status_code})")
    return resp.text


def parse_instruments(html: str) -> list[dict]:
    """Extract (code, symbol, market, label) for every option in the dropdown."""
    soup = BeautifulSoup(html, "html.parser")
    select = soup.find("select", {"id": "instruments"})
    if select is None:
        # Fall back to the name attribute if the id changes.
        select = soup.find("select", {"name": "Instruments"})
    if select is None:
        raise RuntimeError("Could not find the instruments <select> on the page.")

    options = select.find_all("option")
    print(f"  found {len(options)} <option> entries in the dropdown")

    results = []
    for opt in options:
        value = (opt.get("value") or "").strip()
        text  = opt.get_text(strip=True)
        if not value or not value.isdigit():
            continue

        m = LABEL_PATTERN.search(text)
        if not m:
            continue

        symbol = m.group(1)
        market = m.group(2)
        results.append({
            "code":   int(value),
            "symbol": symbol,
            "market": market,
            "label":  text,
        })

    return results


def update_stocks(instruments: list[dict]) -> dict:
    """
    Match parsed instruments against existing stocks by symbol.
    Save instrument_code on matches.

    Returns counters:
        matched   - rows we updated
        skipped_market - parsed but not Main/Junior
        skipped_no_stock - parsed but symbol not in our stocks table
    """
    conn = get_connection()
    try:
        # Build a lookup of existing symbols -> stock_id (so we know which to update).
        rows = conn.execute("SELECT id, symbol FROM stocks").fetchall()
        existing = {r["symbol"]: r["id"] for r in rows}

        matched = 0
        skipped_market = 0
        skipped_no_stock = 0

        for inst in instruments:
            if inst["market"] not in ALLOWED_MARKETS:
                skipped_market += 1
                continue

            sym = inst["symbol"]
            if sym not in existing:
                # We have a code for a stock we don't track yet.
                # That's fine - log it but don't insert (different concern).
                skipped_no_stock += 1
                continue

            conn.execute(
                "UPDATE stocks SET instrument_code = ?, updated_at = datetime('now') "
                "WHERE id = ?",
                (inst["code"], existing[sym]),
            )
            matched += 1

        conn.commit()
        return {
            "matched":          matched,
            "skipped_market":   skipped_market,
            "skipped_no_stock": skipped_no_stock,
        }
    finally:
        conn.close()


def main() -> None:
    html = fetch_page()
    instruments = parse_instruments(html)

    print()
    print(f"Parsed {len(instruments)} instruments total.")
    main_count   = sum(1 for i in instruments if i["market"] == "Main Market")
    junior_count = sum(1 for i in instruments if i["market"] == "Junior Market")
    print(f"  Main Market:   {main_count}")
    print(f"  Junior Market: {junior_count}")
    print(f"  Other:         {len(instruments) - main_count - junior_count}")

    print()
    print("Updating stocks table...")
    result = update_stocks(instruments)
    print(f"  Matched (saved code): {result['matched']}")
    print(f"  Skipped (non-equity market): {result['skipped_market']}")
    print(f"  Skipped (symbol not in our DB): {result['skipped_no_stock']}")

    # Show a few examples of what we just saved.
    print()
    print("Sample updated rows:")
    conn = get_connection()
    try:
        sample = conn.execute(
            "SELECT symbol, name, instrument_code "
            "FROM stocks "
            "WHERE instrument_code IS NOT NULL "
            "ORDER BY symbol LIMIT 5"
        ).fetchall()
        for s in sample:
            print(f"  {s['symbol']:10s} code={s['instrument_code']:5d}  {s['name'][:50]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()