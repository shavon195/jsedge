"""Quick utility: search the stocks table by name fragment.

Usage:
    python scripts/find_stock.py first
    python scripts/find_stock.py rock
    python scripts/find_stock.py liberty
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/find_stock.py <name_fragment>")
        return

    fragment = sys.argv[1]
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol, name FROM stocks WHERE name LIKE ? COLLATE NOCASE ORDER BY symbol",
            (f"%{fragment}%",),
        ).fetchall()
        if not rows:
            print(f"No stocks matching {fragment!r}.")
            return
        print(f"Found {len(rows)} stock(s) matching {fragment!r}:")
        for r in rows:
            print(f"  {r['symbol']:12s} - {r['name']}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()