"""
JSEdge - Daily alert runner.

Single entry point that the scheduler (Windows Task Scheduler now,
real cron after deploy) calls once per day. Performs all the daily
housekeeping for the alerts system:

    1. Refresh stock prices (so target_hit checks use today's prices)
    2. Check the watchlist for any new target hits and fire alerts
    3. Send the WhatsApp keep-alive if 48+ hours since last message
    4. Print a summary (captured to log file by the scheduler)

Designed to be idempotent: re-running it on the same day fires
nothing new (cooldowns + freshness checks handle that). Safe to
schedule conservatively (e.g. every 6 hours) without spamming.

Usage:
    python scripts/run_daily_alerts.py

Exit codes:
    0 - completed (with or without alerts fired)
    1 - hard failure (exception raised by one of the steps)
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.alerts.dispatcher import check_target_hits, send_keep_alive


def _hr(title: str) -> None:
    print()
    print("=" * 60)
    print(f" {title}")
    print("=" * 60)


def main() -> int:
    started_at = datetime.now(timezone.utc)
    print(f"JSEdge daily alert run - {started_at.isoformat()}")
    # ---------------------------------------------------------------
    # 1. Target-hit alerts
    # ---------------------------------------------------------------
    _hr("Checking watchlist for target hits")
    try:
        result = check_target_hits()
        print(f"Checked {result['checked']} active watchlist rows.")
        if result["new_hits"]:
            print(f"NEW HITS ({len(result['new_hits'])}):")
            for h in result["new_hits"]:
                print(f"  - {h['symbol']:8s} delivered via {h['delivered']}")
        else:
            print("No new target hits.")
        if result["skipped"]:
            print(f"Skipped (cooldown or other): {len(result['skipped'])}")
            for s in result["skipped"]:
                print(f"  - {s['symbol']:8s} ({s['reason']})")
        if result["errors"]:
            print(f"ERRORS ({len(result['errors'])}):")
            for e in result["errors"]:
                print(f"  - {e}")
    except Exception as exc:
        print(f"FATAL during target-hit check: {exc}")
        return 1

    # ---------------------------------------------------------------
    # 2. WhatsApp keep-alive
    # ---------------------------------------------------------------
    _hr("WhatsApp keep-alive check")
    try:
        ka = send_keep_alive()
        if ka["sent"]:
            print(f"Keep-alive sent. Verse: {ka.get('verse_ref')}")
            hrs = ka.get("hours_since_last")
            if hrs is not None:
                print(f"({hrs:.1f}h since last outbound WhatsApp)")
        else:
            print(f"Keep-alive skipped: {ka.get('reason') or ka.get('error')}")
    except Exception as exc:
        print(f"FATAL during keep-alive: {exc}")
        return 1

    _hr("Done")
    duration = (datetime.now(timezone.utc) - started_at).total_seconds()
    print(f"Total runtime: {duration:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())