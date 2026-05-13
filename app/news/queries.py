"""
JSEdge - News page query helpers.

Read + write functions for the /news route. Keeps SQL out of main.py
and out of the templates, following the same pattern as
app/fundamentals.py and app/ranking.py.

Public functions:
    list_recent_articles(limit) - fetch articles + their active tags
    list_all_stocks_for_dropdown() - for the manual-add dropdown
    remove_tag(link_id)        - soft-delete a tag
    restore_tag(link_id)       - un-soft-delete a tag (undo)
    add_manual_tag(article_id, stock_id) - create a manual link
"""

from typing import Optional

from app.database import get_connection


def list_recent_articles(limit: int = 50) -> list[dict]:
    """
    Return the most recent articles, each with its active stock tags.

    Each article dict has:
        id, source, url, headline, snippet, published_at, created_at,
        tags: list of dicts with id, stock_id, symbol, name, source,
              confidence, matched_keyword

    "Active" means removed_at IS NULL — soft-deleted links are not shown.
    """
    conn = get_connection()
    try:
        article_rows = conn.execute(
            """
            SELECT id, source, url, headline, snippet, published_at,
                   ai_summary, scraped_at
            FROM news_articles
            ORDER BY COALESCE(published_at, scraped_at) DESC,
                     id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall() 

        if not article_rows:
            return []

        article_ids = [r["id"] for r in article_rows]
        placeholders = ",".join("?" * len(article_ids))

        tag_rows = conn.execute(
            f"""
            SELECT l.id              AS link_id,
                   l.article_id      AS article_id,
                   l.stock_id        AS stock_id,
                   l.source          AS link_source,
                   l.confidence      AS confidence,
                   l.matched_keyword AS matched_keyword,
                   s.symbol          AS symbol,
                   s.name            AS name
            FROM news_stock_links l
            JOIN stocks s ON s.id = l.stock_id
            WHERE l.article_id IN ({placeholders})
              AND l.removed_at IS NULL
            ORDER BY
                CASE l.source
                    WHEN 'manual'   THEN 1
                    WHEN 'auto'     THEN 2
                    WHEN 'thematic' THEN 3
                    ELSE 4
                END,
                s.symbol
            """,
            tuple(article_ids),
        ).fetchall()

        # Group tags by article_id.
        tags_by_article: dict[int, list[dict]] = {aid: [] for aid in article_ids}
        for t in tag_rows:
            tags_by_article[t["article_id"]].append({
                "link_id":         t["link_id"],
                "stock_id":        t["stock_id"],
                "symbol":          t["symbol"],
                "name":            t["name"],
                "source":          t["link_source"],
                "confidence":      t["confidence"],
                "matched_keyword": t["matched_keyword"],
            })

        # Build the result list, preserving article order.
        result: list[dict] = []
        for row in article_rows:
            result.append({
                "id":           row["id"],
                "source":       row["source"],
                "url":          row["url"],
                "headline":     row["headline"],
                "snippet":      row["snippet"],
                "published_at": row["published_at"],
                "ai_summary":   row["ai_summary"],
                "scraped_at":   row["scraped_at"],
                "tags":         tags_by_article.get(row["id"], []),
            })
        return result
    finally:
        conn.close()


def list_all_stocks_for_dropdown() -> list[dict]:
    """
    Return all listed stocks for use in the manual-tag dropdown.

    Each dict has: id, symbol, name. Sorted by symbol.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, symbol, name
            FROM stocks
            WHERE is_listed = 1
            ORDER BY symbol
            """,
        ).fetchall()
        return [{"id": r["id"], "symbol": r["symbol"], "name": r["name"]}
                for r in rows]
    finally:
        conn.close()


def remove_tag(link_id: int) -> bool:
    """
    Soft-delete a single news_stock_links row by setting removed_at.

    Returns True if a row was updated, False if no matching active row.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            UPDATE news_stock_links
            SET removed_at = datetime('now')
            WHERE id = ? AND removed_at IS NULL
            """,
            (link_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def restore_tag(link_id: int) -> bool:
    """
    Un-soft-delete a single news_stock_links row.

    Returns True if a row was updated, False if no matching soft-deleted row.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            UPDATE news_stock_links
            SET removed_at = NULL
            WHERE id = ? AND removed_at IS NOT NULL
            """,
            (link_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def add_manual_tag(article_id: int, stock_id: int) -> Optional[int]:
    """
    Create a new manual link between an article and a stock.

    If a soft-deleted row already exists for this pair, restore it
    instead of inserting a duplicate (and flip source to 'manual').
    If an active row already exists for this pair, do nothing and
    return None.

    Returns:
        link_id on success, None if a duplicate active link already exists.
    """
    conn = get_connection()
    try:
        # Check for any existing row for this pair.
        existing = conn.execute(
            "SELECT id, removed_at FROM news_stock_links "
            "WHERE article_id = ? AND stock_id = ?",
            (article_id, stock_id),
        ).fetchone()

        if existing is not None:
            if existing["removed_at"] is None:
                # Already an active link — nothing to do.
                return None
            # Soft-deleted: restore and re-label as manual.
            conn.execute(
                """
                UPDATE news_stock_links
                SET removed_at = NULL,
                    source = 'manual',
                    confidence = 1.0,
                    matched_keyword = 'user-added'
                WHERE id = ?
                """,
                (existing["id"],),
            )
            conn.commit()
            return existing["id"]

        # No row at all — fresh insert.
        cursor = conn.execute(
            """
            INSERT INTO news_stock_links
                (article_id, stock_id, source, confidence, matched_keyword)
            VALUES (?, ?, 'manual', 1.0, 'user-added')
            """,
            (article_id, stock_id),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()