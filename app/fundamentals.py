"""
JSEdge — Fundamentals data layer.

Functions for querying and writing fundamentals data:
- list_stocks_with_status() : list all stocks + how many fundamental rows each has
- get_fundamentals_for_stock() : fetch all fundamental rows for one stock
- get_fundamental_by_id()    : fetch a single row for editing
- save_fundamental()          : insert or update one row
- delete_fundamental()        : remove a row by id

The form (in main.py) calls these functions. Keeping data logic out of
the route handlers makes it testable and easier to swap in a scraper
later (it'll call the same save_fundamental() function).
"""

import logging
from typing import Optional

from app.database import get_connection

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# List view: every stock + their fundamentals coverage
# ---------------------------------------------------------------------------
def list_stocks_with_status() -> list[dict]:
    """
    Return all stocks joined with a count of how many fundamental rows
    they have, sorted by emptiest-first so the user knows where to focus.

    Returns:
        List of dicts with keys: id, symbol, name, market, fundamentals_count
    """
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT
                s.id,
                s.symbol,
                s.name,
                s.market,
                COUNT(f.id) AS fundamentals_count
            FROM stocks s
            LEFT JOIN fundamentals f ON f.stock_id = s.id
            WHERE s.is_listed = 1
            GROUP BY s.id, s.symbol, s.name, s.market
            ORDER BY fundamentals_count ASC, s.symbol ASC
        """).fetchall()
    finally:
        conn.close()

    return [dict(r) for r in rows]

# ---------------------------------------------------------------------------
# Single-stock view: fetch one stock + all its fundamentals
# ---------------------------------------------------------------------------
def get_stock_with_fundamentals(stock_id: int) -> Optional[dict]:
    """
    Fetch one stock by id, plus all its existing fundamentals rows.

    Args:
        stock_id: the stock's database id.

    Returns:
        Dict with keys 'stock' (the stock dict) and 'fundamentals'
        (list of fundamental rows, newest first), or None if stock
        doesn't exist.
    """
    conn = get_connection()
    try:
        stock_row = conn.execute(
            "SELECT id, symbol, name, market, sector, currency "
            "FROM stocks WHERE id = ?",
            (stock_id,),
        ).fetchone()

        if stock_row is None:
            return None

        fundamentals_rows = conn.execute(
            """
            SELECT * FROM fundamentals
            WHERE stock_id = ?
            ORDER BY period_end_date DESC, period_type ASC
            """,
            (stock_id,),
        ).fetchall()
    finally:
        conn.close()

    return {
        "stock":        dict(stock_row),
        "fundamentals": [dict(r) for r in fundamentals_rows],
    }