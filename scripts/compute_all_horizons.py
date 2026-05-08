"""
JSEdge — Compute and persist scores for ALL horizons in one shot.

For a given date, runs score_all_stocks() for each horizon in
HORIZON_WEIGHTS and saves results to the scores table.

After this, the scores table has one row per (stock, date, horizon)
combination — feeding the dashboard's horizon dropdown.

Usage:
    python scripts/compute_all_horizons.py
    python scripts/compute_all_horizons.py --date 2026-04-28
"""

import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection
from app.ranking import (
    HORIZON_WEIGHTS,
    score_all_stocks,
    save_scores_to_db,
)


def find_latest_price_date() -> str | None:
    """Look up the most recent date in prices_daily."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT MAX(date) AS latest FROM prices_daily"
        ).fetchone()
        return row["latest"] if row and row["latest"] else None
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute scores for all horizons for a given date."
    )
    parser.add_argument(
        "--date",
        help="Trading date (YYYY-MM-DD). Defaults to latest in prices_daily.",
    )
    args = parser.parse_args()

    if args.date:
        target_date = date.fromisoformat(args.date)
    else:
        latest = find_latest_price_date()
        if not latest:
            print("❌ No price data found. Run the scraper first.")
            sys.exit(1)
        target_date = date.fromisoformat(latest)

    print("=" * 60)
    print(f"JSEdge — Scoring for {target_date.isoformat()}")
    print(f"Horizons: {', '.join(HORIZON_WEIGHTS.keys())}")
    print("=" * 60)

    total_saved = 0
    total_skipped = 0

    for horizon in HORIZON_WEIGHTS.keys():
        print(f"\n📊 {horizon}")
        results = score_all_stocks(target_date, horizon)
        save_result = save_scores_to_db(results, target_date)
        print(f"   Saved: {save_result['saved']}  |  Skipped: {save_result['skipped']}")
        total_saved += save_result["saved"]
        total_skipped += save_result["skipped"]

    print()
    print("=" * 60)
    print(f"✅ Done. Total: {total_saved} rows saved, {total_skipped} skipped.")
    print(f"    Expected: ~{len(HORIZON_WEIGHTS) * 101} rows in scores table.")
    print("=" * 60)


if __name__ == "__main__":
    main()