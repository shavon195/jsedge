"""Quick utility: inspect all news_stock_links rows for a given stock symbol.

Shows source, removed_at state, and the article headline so you can verify
soft-delete behavior.

Usage:
    python scripts/check_tag.py DCOVE
    python scripts/check_tag.py NCBFG
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/check_tag.py <symbol>")
        return

    symbol = sys.argv[1].upper()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT l.id           AS link_id,
                   l.article_id   AS article_id,
                   l.source       AS source,
                   l.removed_at   AS removed_at,
                   a.headline     AS headline,
                   s.symbol       AS symbol
            FROM news_stock_links l
            JOIN news_articles a ON a.id = l.article_id
            JOIN stocks        s ON s.id = l.stock_id
            WHERE s.symbol = ?
            ORDER BY l.id
            """,
            (symbol,),
        ).fetchall()

        if not rows:
            print(f"No news_stock_links rows for symbol {symbol!r}.")
            return

        print(f"Found {len(rows)} link(s) for {symbol}:")
        print()
        for r in rows:
            status = "REMOVED" if r["removed_at"] else "ACTIVE"
            removed_info = f" (at {r['removed_at']})" if r["removed_at"] else ""
            print(f"  link_id={r['link_id']:4d}  {status:7s}{removed_info}")
            print(f"    source:    {r['source']}")
            print(f"    article:   [{r['article_id']}] {r['headline'][:70]}")
            print()
    finally:
        conn.close()


if __name__ == "__main__":
    main()