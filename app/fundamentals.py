"""
JSEdge — Fundamentals data layer.

Functions for querying and writing fundamentals data:
- list_stocks_with_status() : list all stocks + how many fundamental rows each has
- get_stock_with_fundamentals() : fetch one stock + its fundamentals
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
                COUNT(f.id)         AS fundamentals_count,
                MAX(f.updated_at)   AS last_updated
            FROM stocks s
            LEFT JOIN fundamentals f ON f.stock_id = s.id
            WHERE s.is_listed = 1
            GROUP BY s.id, s.symbol, s.name, s.market
            ORDER BY fundamentals_count ASC,
                     last_updated ASC NULLS FIRST,
                     s.symbol ASC
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


# ---------------------------------------------------------------------------
# Fetch one fundamental row by its id (for view/edit pages)
# ---------------------------------------------------------------------------
def get_fundamental_by_id(fundamental_id: int) -> Optional[dict]:
    """Fetch one fundamental row joined with its stock info."""
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT f.*,
                   s.symbol, s.name AS stock_name, s.market
            FROM fundamentals f
            JOIN stocks s ON s.id = f.stock_id
            WHERE f.id = ?
            """,
            (fundamental_id,),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Save: insert or update a fundamentals row
# ---------------------------------------------------------------------------
def save_fundamental(stock_id: int, form_data: dict) -> dict:
    """
    Insert or update a single fundamentals row.

    Uses ON CONFLICT(stock_id, period_end_date, period_type) so re-saving
    the same period updates the existing row instead of failing.

    Args:
        stock_id:  the stock's database id.
        form_data: dict from the submitted HTML form. Must include
                   'period_end_date' and 'period_type'. All other fields
                   are optional and stored as NULL if missing/empty.

    Returns:
        Dict with keys:
            success (bool)
            action  ('inserted' | 'updated')
            errors  (list of error strings — empty if success)
    """
    errors = []

    # --- required fields ---
    period_end_date = form_data.get("period_end_date", "").strip()
    period_type     = form_data.get("period_type", "").strip()

    if not period_end_date:
        errors.append("Period end date is required.")
    if period_type not in ("quarterly", "half_year", "annual", "ttm"):
        errors.append("Period type must be quarterly, half_year, annual, or ttm.")

    if errors:
        return {"success": False, "action": None, "errors": errors}

    # --- helper to convert form strings to floats / None ---
    def to_float(field: str):
        raw = form_data.get(field, "")
        if raw is None:
            return None
        raw = str(raw).strip()
        if raw == "":
            return None
        try:
            return float(raw)
        except ValueError:
            errors.append(f"'{field}' must be a number (got: {raw!r}).")
            return None

    # Numeric fields — all optional.
    numeric_fields = [
        "eps", "dividend_per_share",
        "total_debt", "total_equity", "total_assets",
        "net_income", "operating_income",
        "operating_cash_flow", "free_cash_flow",
        "revenue", "shares_outstanding",
    ]
    values = {f: to_float(f) for f in numeric_fields}

    # Notes — string, optional.
    notes = (form_data.get("notes") or "").strip() or None

    if errors:
        return {"success": False, "action": None, "errors": errors}

    # --- check whether this period already exists (insert vs update) ---
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM fundamentals "
            "WHERE stock_id = ? AND period_end_date = ? AND period_type = ?",
            (stock_id, period_end_date, period_type),
        ).fetchone()

        action = "updated" if existing else "inserted"

        conn.execute(
            """
            INSERT INTO fundamentals (
                stock_id, period_end_date, period_type,
                eps, dividend_per_share,
                total_debt, total_equity, total_assets,
                net_income, operating_income,
                operating_cash_flow, free_cash_flow,
                revenue, shares_outstanding,
                source, notes
            ) VALUES (
                ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                'manual', ?
            )
            ON CONFLICT(stock_id, period_end_date, period_type) DO UPDATE SET
                eps                 = excluded.eps,
                dividend_per_share  = excluded.dividend_per_share,
                total_debt          = excluded.total_debt,
                total_equity        = excluded.total_equity,
                total_assets        = excluded.total_assets,
                net_income          = excluded.net_income,
                operating_income    = excluded.operating_income,
                operating_cash_flow = excluded.operating_cash_flow,
                free_cash_flow      = excluded.free_cash_flow,
                revenue             = excluded.revenue,
                shares_outstanding  = excluded.shares_outstanding,
                notes               = excluded.notes,
                updated_at          = datetime('now')
            """,
            (
                stock_id, period_end_date, period_type,
                values["eps"], values["dividend_per_share"],
                values["total_debt"], values["total_equity"], values["total_assets"],
                values["net_income"], values["operating_income"],
                values["operating_cash_flow"], values["free_cash_flow"],
                values["revenue"], values["shares_outstanding"],
                notes,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    log.info(
        "Fundamental %s for stock_id=%d, period=%s/%s",
        action, stock_id, period_end_date, period_type,
    )
    return {"success": True, "action": action, "errors": []}


# ---------------------------------------------------------------------------
# Delete one fundamental row
# ---------------------------------------------------------------------------
def delete_fundamental(fundamental_id: int) -> bool:
    """Delete a fundamental row by id. Returns True if a row was deleted."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM fundamentals WHERE id = ?",
            (fundamental_id,),
        )
        conn.commit()
        deleted = cursor.rowcount > 0
    finally:
        conn.close()

    if deleted:
        log.info("Deleted fundamental id=%d", fundamental_id)
    else:
        log.warning("Tried to delete non-existent fundamental id=%d", fundamental_id)

    return deleted

# ---------------------------------------------------------------------------
# Navigation helper — find the prev/next stock relative to one we're viewing
# ---------------------------------------------------------------------------
def get_prev_next_stocks(stock_id: int) -> dict:
    """
    Find the stock alphabetically before and after the given stock.

    Used to power Prev / Next navigation on the per-stock fundamentals page.

    Args:
        stock_id: the current stock's id.

    Returns:
        Dict with keys 'prev' and 'next', each being a dict of
        {id, symbol} or None if there is no prev/next.
    """
    conn = get_connection()
    try:
        # Pull all listed stocks ordered by symbol (matches the list page).
        rows = conn.execute(
            "SELECT id, symbol FROM stocks WHERE is_listed = 1 "
            "ORDER BY symbol ASC"
        ).fetchall()
    finally:
        conn.close()

    stocks = [dict(r) for r in rows]

    # Find current stock's position.
    current_index = None
    for i, s in enumerate(stocks):
        if s["id"] == stock_id:
            current_index = i
            break

    if current_index is None:
        return {"prev": None, "next": None}

    prev_stock = stocks[current_index - 1] if current_index > 0 else None
    next_stock = stocks[current_index + 1] if current_index < len(stocks) - 1 else None

    return {"prev": prev_stock, "next": next_stock}