"""Quick lookup: find JSE symbols by company name keyword."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection


# Search for these company name fragments
SEARCH_TERMS = [
    "TEAS",
    "JAMAICAN TEAS",
    "JAMT",
]


def main() -> None:
    conn = get_connection()
    try:
        for term in SEARCH_TERMS:
            print(f"\n=== Searching for: {term} ===")
            rows = conn.execute(
                "SELECT symbol, name FROM stocks WHERE is_listed = 1 "
                "AND UPPER(name) LIKE ? ORDER BY symbol",
                (f"%{term}%",),
            ).fetchall()

            if rows:
                for r in rows:
                    print(f"  {r['symbol']:<12} {r['name']}")
            else:
                print(f"  (no matches)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()