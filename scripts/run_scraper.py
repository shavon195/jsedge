"""
JSEdge — Daily scraper run.

Fetches both Main and Junior market trade quotes for a given date,
parses them, and saves to the database.

Usage:
    python scripts/run_scraper.py                  # uses today's date
    python scripts/run_scraper.py --date 2026-04-28  # specific date
    python scripts/run_scraper.py --offline        # use saved sample HTML

Run from the project root with the venv activated.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

# Allow imports from the project root.
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.scraper import (
    fetch_trade_quotes_page,
    load_sample_html,
    parse_all_stocks,
    save_stocks_to_db,
    save_prices_to_db,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run JSEdge daily scrape.")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=date.today(),
        help="Trading date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use saved sample HTML instead of hitting the live site.",
    )
    return parser.parse_args()


def run_market(market: str, target_date: date, offline: bool) -> dict:
    """Scrape one market and save to DB. Returns counts."""
    print(f"\n--- {market.title()} Market ---")

    if offline:
        html = load_sample_html(market)
    else:
        html = fetch_trade_quotes_page(market, target_date)

    stocks = parse_all_stocks(html)

    if not stocks:
        print(f"  No stocks parsed — possibly a non-trading day.")
        return {"stocks": 0, "prices": 0}

    stock_result = save_stocks_to_db(stocks, market)
    price_result = save_prices_to_db(stocks, target_date)

    print(
        f"  Stocks: {stock_result['inserted']} inserted, "
        f"{stock_result['updated']} updated"
    )
    print(
        f"  Prices: {price_result['saved']} saved, "
        f"{price_result['skipped']} skipped"
    )
    return {"stocks": len(stocks), "prices": price_result["saved"]}


def main() -> None:
    args = parse_args()

    print("=" * 60)
    print(f"JSEdge — Daily scrape for {args.date.isoformat()}")
    print(f"Mode: {'OFFLINE (sample files)' if args.offline else 'LIVE'}")
    print("=" * 60)

    main_result   = run_market("main",   args.date, args.offline)
    junior_result = run_market("junior", args.date, args.offline)

    total_stocks = main_result["stocks"] + junior_result["stocks"]
    total_prices = main_result["prices"] + junior_result["prices"]

    print()
    print("=" * 60)
    print(f"  Total stocks parsed:  {total_stocks}")
    print(f"  Total prices saved:   {total_prices}")
    print("=" * 60)


if __name__ == "__main__":
    main()