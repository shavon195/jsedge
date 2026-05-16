"""
JSEdge - Watchlist data access.

Single-user (admin-only) watchlist for tracking JSE stocks with target
buy prices. When the actual price hits the target, an alert can fire
(alert logic is a separate feature, built next).

Public functions:
    list_watchlist(state)       - return all watchlist rows + current price + gap
    add_to_watchlist(stock_id)  - start tracking a stock
    update_watchlist(id, ...)   - change limit_price / notes / is_active
    remove_from_watchlist(id)   - delete a watchlist row
    is_on_watchlist(stock_id)   - bool, used for ranking-page button state
"""

from typing import Optional

from app.database import get_connection


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------
def list_watchlist(state: str = "active") -> list[dict]:
    """
    Return watchlist rows joined with stocks + the latest price.

    Args:
        state: 'active' (default), 'inactive', or 'all'.

    Each dict has:
        id, stock_id, symbol, name, market,
        limit_price, target_shares, notes, is_active,
        added_at, updated_at,
        current_price (latest close, may be None),
        gap_pct (signed % from current to target, may be None),
        gap_state ('hit' | 'near' | 'far' | None)
    """
    where = ""
    if state == "active":
        where = "WHERE w.is_active = 1"
    elif state == "inactive":
        where = "WHERE w.is_active = 0"

    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT
                w.id              AS id,
                w.stock_id        AS stock_id,
                w.limit_price     AS limit_price,
                w.target_shares   AS target_shares,
                w.notes           AS notes,
                w.is_active       AS is_active,
                w.added_at        AS added_at,
                w.updated_at      AS updated_at,
                s.symbol          AS symbol,
                s.name            AS name,
                s.market          AS market,
                (SELECT p.close_price
                   FROM prices_daily p
                  WHERE p.stock_id = w.stock_id
                  ORDER BY p.date DESC
                  LIMIT 1)        AS current_price
            FROM watchlist w
            JOIN stocks s ON s.id = w.stock_id
            {where}
            ORDER BY w.added_at DESC
            """,
        ).fetchall()

        result: list[dict] = []
        for r in rows:
            current = r["current_price"]
            target  = r["limit_price"]
            gap_pct: Optional[float] = None
            gap_state: Optional[str] = None
            if current is not None and target is not None and target > 0:
                gap_pct = (current - target) / target * 100.0
                if abs(gap_pct) < 0.5:
                    gap_state = "hit"
                elif abs(gap_pct) <= 5.0:
                    gap_state = "near"
                else:
                    gap_state = "far"

            result.append({
                "id":            r["id"],
                "stock_id":      r["stock_id"],
                "symbol":        r["symbol"],
                "name":          r["name"],
                "market":        r["market"],
                "limit_price":   target,
                "target_shares": r["target_shares"],
                "notes":         r["notes"],
                "is_active":     bool(r["is_active"]),
                "added_at":      r["added_at"],
                "updated_at":    r["updated_at"],
                "current_price": current,
                "gap_pct":       gap_pct,
                "gap_state":     gap_state,
            })
        return result
    finally:
        conn.close()


def is_on_watchlist(stock_id: int) -> bool:
    """True if this stock is currently in the watchlist (active or inactive)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM watchlist WHERE stock_id = ?",
            (stock_id,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_watched_stock_ids() -> set[int]:
    """Return the set of stock_ids currently on the watchlist (any state).

    Used by the JSE rankings page to mark which rows already have a star.
    """
    conn = get_connection()
    try:
        rows = conn.execute("SELECT stock_id FROM watchlist").fetchall()
        return {r["stock_id"] for r in rows}
    finally:
        conn.close()

def get_watched_symbols() -> set[str]:
    """Return the set of stock symbols currently on the watchlist.

    Used by the JSE rankings page (which works with symbols, not ids)
    to mark which rows are already watched.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT s.symbol AS symbol "
            "FROM watchlist w JOIN stocks s ON s.id = w.stock_id"
        ).fetchall()
        return {r["symbol"] for r in rows}
    finally:
        conn.close()


def add_to_watchlist_by_symbol(symbol: str) -> Optional[int]:
    """Look up the stock by symbol, then call add_to_watchlist.

    Returns the watchlist row id on success, or None if the symbol
    doesn't exist OR the stock is already on the watchlist (active).
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM stocks WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        if row is None:
            return None
        stock_id = row["id"]
    finally:
        conn.close()

    return add_to_watchlist(stock_id)

def watchlist_counts() -> dict:
    """Return {active, hit, inactive} counts for the filter toggle."""
    conn = get_connection()
    try:
        active = conn.execute(
            "SELECT COUNT(*) AS n FROM watchlist WHERE is_active = 1"
        ).fetchone()["n"]
        inactive = conn.execute(
            "SELECT COUNT(*) AS n FROM watchlist WHERE is_active = 0"
        ).fetchone()["n"]
    finally:
        conn.close()

    # Hit count requires gap computation; reuse list_watchlist for accuracy.
    actives = list_watchlist(state="active")
    hit = sum(1 for w in actives if w["gap_state"] == "hit")

    return {"active": active, "hit": hit, "inactive": inactive}


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
def add_to_watchlist(stock_id: int) -> Optional[int]:
    """
    Start tracking a stock. Returns the new row id, or None if it
    was already on the list (we don't surface this as an error - we
    just re-activate any inactive row for the same stock).
    """
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id, is_active FROM watchlist WHERE stock_id = ?",
            (stock_id,),
        ).fetchone()

        if existing is not None:
            if not existing["is_active"]:
                conn.execute(
                    "UPDATE watchlist "
                    "SET is_active = 1, updated_at = datetime('now') "
                    "WHERE id = ?",
                    (existing["id"],),
                )
                conn.commit()
                return existing["id"]
            return None  # already active, nothing to do

        cursor = conn.execute(
            "INSERT INTO watchlist (stock_id) VALUES (?)",
            (stock_id,),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_watchlist(
    watchlist_id: int,
    limit_price:   Optional[float] = None,
    target_shares: Optional[int]   = None,
    notes:         Optional[str]   = None,
    is_active:     Optional[bool]  = None,
) -> bool:
    """
    Update one or more fields on a watchlist row. Returns True if a
    row was updated, False if no matching row.

    Any field left as None is left unchanged.
    """
    fields: list[str] = []
    values: list = []
    if limit_price is not None:
        fields.append("limit_price = ?")
        values.append(limit_price)
    if target_shares is not None:
        fields.append("target_shares = ?")
        values.append(target_shares)
    if notes is not None:
        fields.append("notes = ?")
        values.append(notes)
    if is_active is not None:
        fields.append("is_active = ?")
        values.append(1 if is_active else 0)

    if not fields:
        return False

    fields.append("updated_at = datetime('now')")
    values.append(watchlist_id)

    conn = get_connection()
    try:
        cursor = conn.execute(
            f"UPDATE watchlist SET {', '.join(fields)} WHERE id = ?",
            tuple(values),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def remove_from_watchlist(watchlist_id: int) -> bool:
    """Delete a watchlist row. Returns True if a row was deleted."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM watchlist WHERE id = ?",
            (watchlist_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()