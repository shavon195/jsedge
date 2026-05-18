"""
JSEdge - Diagnostic: count duplicate (stock_id, horizon) rows in scores.

The scores table is supposed to have one row per (stock_id, horizon)
combination. This script reports how many rows have duplicates and
lists the worst offenders.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection


def main() -> None:
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) AS n FROM scores").fetchone()["n"]
        unique = conn.execute(
            "SELECT COUNT(*) AS n FROM ("
            "  SELECT DISTINCT stock_id, horizon FROM scores"
            ")"
        ).fetchone()["n"]

        print(f"Total rows in scores:                {total}")
        print(f"Unique (stock_id, horizon) pairs:    {unique}")
        print(f"Duplicate rows:                      {total - unique}")
        print()

        if total == unique:
            print("No duplicates. The table is clean.")
            return

        # Show the (stock_id, horizon) pairs with the most duplicates.
        rows = conn.execute(
            "SELECT s.symbol, sc.horizon, COUNT(*) AS n "
            "FROM scores sc JOIN stocks s ON s.id = sc.stock_id "
            "GROUP BY sc.stock_id, sc.horizon "
            "HAVING COUNT(*) > 1 "
            "ORDER BY n DESC LIMIT 20"
        ).fetchall()
        print(f"Top duplicate pairs (showing up to 20):")
        for r in rows:
            print(f"  {r['symbol']:12s} {r['horizon']:10s} appears {r['n']} times")
    finally:
        conn.close()


if __name__ == "__main__":
    main()