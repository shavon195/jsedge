"""
JSEdge - Weekly catch-up backfill.

Designed to run once a week (e.g. Sundays). For each stock that has
an instrument_code, fetches the last 30 days of price history and
inserts any missing rows. The daily scrape already covers most days,
so this is just safety net for:
    - Newly-listed JSE stocks discovered by run_scraper.py's
      instrument-discovery step
    - Days where the daily scrape missed (server outage, holiday)
    - Stocks added to JSEdge for the first time

Idempotent: rows already in prices_daily are skipped.

Usage:
    python scripts/weekly_backfill_catchup.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Re-use the heavy lifting from backfill_price_history.py
from scripts.backfill_price_history import main as backfill_main


def main() -> int:
    # Simulate command-line args for the backfill script.
    # We always want: --days 30, all stocks (no --symbol), live (no --dry-run)
    sys.argv = ["weekly_backfill_catchup.py", "--days", "30"]
    return backfill_main()


if __name__ == "__main__":
    sys.exit(main())