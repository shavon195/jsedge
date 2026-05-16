"""
JSEdge - Bulk backfill of historical daily prices from the JSE
Price History page.

For each stock with an instrument_code, fetches a configurable date
range of historical daily prices and inserts them into prices_daily.
Idempotent: rows already in prices_daily are skipped via INSERT OR
IGNORE (or replaced if we want fresh data).

Designed to be polite to JSE's server: 1.5s sleep between requests.

Usage:
    python scripts/backfill_price_history.py                 # 1 year, all stocks
    python scripts/backfill_price_history.py --days 180      # custom range
    python scripts/backfill_price_history.py --symbol CAR    # one stock only
    python scripts/backfill_price_history.py --dry-run       # don't write anything
"""

import argparse
import re
import sys
import time
from datetime import date, datetime, timedelta
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

# Polite delay between stocks (seconds).
SLEEP_BETWEEN_REQUESTS = 1.5

# Request timeout (seconds).
REQUEST_TIMEOUT = 30


def parse_price_table(html: str) -> list[dict]:
    """
    Parse the price history table out of one page response.

    Returns a list of dicts:
        {"date": "YYYY-MM-DD", "close_price": float, "volume": int}

    Skips rows with missing/unparseable data.
    """
    soup = BeautifulSoup(html, "html.parser")

    # The price table is the largest <table> on the page.
    # Find all tables and pick the one with the most rows.
    tables = soup.find_all("table")
    if not tables:
        return []

    best_table = max(tables, key=lambda t: len(t.find_all("tr")))
    rows = best_table.find_all("tr")
    if len(rows) < 2:
        return []

    # Identify the columns by header row.
    header_cells = [c.get_text(strip=True).upper() for c in rows[0].find_all(["th", "td"])]
    try:
        date_idx   = header_cells.index("DATE")
    except ValueError:
        return []

    # Find CLOSING PRICE and VOLUME columns (the labels span two lines in the HTML
    # so look for keywords).
    close_idx  = None
    volume_idx = None
    for i, h in enumerate(header_cells):
        if "CLOSING" in h and "PRICE" in h:
            close_idx = i
        elif h == "VOLUME":
            volume_idx = i

    if close_idx is None:
        return []

    results = []
    for tr in rows[1:]:
        cells = tr.find_all(["td", "th"])
        if len(cells) <= close_idx:
            continue

        date_str  = cells[date_idx].get_text(strip=True)
        close_str = cells[close_idx].get_text(strip=True).replace(",", "")
        vol_str   = cells[volume_idx].get_text(strip=True).replace(",", "") if volume_idx is not None else ""

        if not date_str or not close_str:
            continue

        # Date format on JSE page: "YYYY-MM-DD"
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            continue

        try:
            close_price = float(close_str)
        except ValueError:
            continue

        try:
            volume = int(vol_str) if vol_str else None
        except ValueError:
            volume = None

        results.append({
            "date":        date_str,
            "close_price": close_price,
            "volume":      volume,
        })

    return results


def fetch_stock_history(code: int, from_date: str, thru_date: str) -> list[dict]:
    """Hit the JSE price-history page for one stock + date range."""
    params = {
        "instrumentCode": code,
        "fromDate":       from_date,
        "thruDate":       thru_date,
    }
    resp = requests.get(URL, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return parse_price_table(resp.text)


def save_rows(stock_id: int, rows: list[dict], dry_run: bool = False) -> dict:
    """Insert rows into prices_daily. Skip duplicates."""
    if dry_run or not rows:
        return {"inserted": 0, "skipped": 0}

    conn = get_connection()
    try:
        inserted = 0
        skipped  = 0
        for r in rows:
            try:
                conn.execute(
                    "INSERT INTO prices_daily (stock_id, date, close_price, volume) "
                    "VALUES (?, ?, ?, ?)",
                    (stock_id, r["date"], r["close_price"], r["volume"]),
                )
                inserted += 1
            except Exception:
                # UNIQUE constraint violation on (stock_id, date).
                skipped += 1
        conn.commit()
        return {"inserted": inserted, "skipped": skipped}
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill JSE price history.")
    parser.add_argument("--days", type=int, default=365,
                        help="How many days back to fetch (default: 365)")
    parser.add_argument("--symbol", type=str, default=None,
                        help="Only backfill this single symbol (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and report, but don't write to DB")
    args = parser.parse_args()

    thru_date = date.today()
    from_date = thru_date - timedelta(days=args.days)
    from_str  = from_date.strftime("%Y-%m-%d")
    thru_str  = thru_date.strftime("%Y-%m-%d")

    # Pick which stocks to backfill.
    conn = get_connection()
    try:
        if args.symbol:
            rows = conn.execute(
                "SELECT id, symbol, instrument_code FROM stocks "
                "WHERE symbol = ? AND instrument_code IS NOT NULL",
                (args.symbol.upper(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, symbol, instrument_code FROM stocks "
                "WHERE instrument_code IS NOT NULL "
                "ORDER BY symbol"
            ).fetchall()
    finally:
        conn.close()

    if not rows:
        print(f"No stocks to backfill (symbol={args.symbol}). Did you run "
              f"fetch_instrument_codes.py first?")
        return 1

    print("=" * 60)
    print(f"JSEdge - Historical price backfill")
    print(f"  Date range: {from_str} - {thru_str}  ({args.days} days)")
    print(f"  Stocks:     {len(rows)}")
    print(f"  Mode:       {'DRY-RUN (no writes)' if args.dry_run else 'LIVE'}")
    print("=" * 60)

    total_inserted = 0
    total_skipped  = 0
    total_fetched  = 0
    failures: list[str] = []

    started_at = time.time()
    for i, r in enumerate(rows, start=1):
        sym  = r["symbol"]
        code = r["instrument_code"]
        sid  = r["id"]
        try:
            data = fetch_stock_history(code, from_str, thru_str)
            total_fetched += len(data)
            save = save_rows(sid, data, dry_run=args.dry_run)
            total_inserted += save["inserted"]
            total_skipped  += save["skipped"]
            print(f"  [{i:3d}/{len(rows)}] {sym:10s} code={code:<6d} "
                  f"fetched={len(data):3d}  "
                  f"inserted={save['inserted']:3d}  "
                  f"skipped={save['skipped']:3d}")
        except requests.RequestException as e:
            err = f"{sym}: {str(e)[:80]}"
            failures.append(err)
            print(f"  [{i:3d}/{len(rows)}] {sym:10s} FAILED ({err})")
        except Exception as e:
            err = f"{sym}: {str(e)[:80]}"
            failures.append(err)
            print(f"  [{i:3d}/{len(rows)}] {sym:10s} UNEXPECTED ({err})")

        # Be polite to JSE.
        if i < len(rows):
            time.sleep(SLEEP_BETWEEN_REQUESTS)

    elapsed = time.time() - started_at

    print("=" * 60)
    print(f"  Total rows fetched:   {total_fetched}")
    print(f"  Total rows inserted:  {total_inserted}")
    print(f"  Total rows skipped:   {total_skipped} (duplicates)")
    print(f"  Failures:             {len(failures)}")
    print(f"  Elapsed:              {elapsed:.1f}s")
    print("=" * 60)

    if failures:
        print("Failures:")
        for f in failures[:10]:
            print(f"  - {f}")
        if len(failures) > 10:
            print(f"  ... and {len(failures) - 10} more")

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())