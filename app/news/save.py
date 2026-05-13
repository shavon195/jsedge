"""
JSEdge — News database save pipeline (source-agnostic).

Persists a batch of scraped articles to the database. Works for any
news source — the article dicts coming in just need the standard shape:

    {
        "source":          str,          # e.g. "gleaner", "observer"
        "url":             str,          # unique
        "headline":        str,
        "snippet":         str | None,
        "published_at":    str | None,
        "matched_stocks":  list[str],    # symbols directly mentioned
        "matched_themes":  list[dict],   # from article_relevance()
        "matched_macros":  list[str],    # not yet persisted, future use
    }

Save behavior:
    - INSERT new articles by URL; UPDATE headline/snippet on re-scrape
      but PRESERVE ai_summary (Save Q1 = C)
    - Clear AUTO and THEMATIC links on re-save, leave MANUAL links
      intact (Save Q2 = C)
"""

import logging

from app.database import get_connection
from app.news_keywords import STOCK_KEYWORDS

log = logging.getLogger(__name__)


def save_articles_to_db(articles: list[dict]) -> dict:
    """
    Save a batch of scraped articles to the database.

    For each article:
        1. INSERT into news_articles (uses UNIQUE(url) for dedupe).
           - If URL exists: UPDATE headline/snippet but PRESERVE ai_summary.
        2. Delete any existing AUTO and THEMATIC links for this article,
           leaving any MANUAL links intact.
        3. INSERT fresh auto links (direct stock mentions).
        4. INSERT fresh thematic links (stocks via theme matches).

    Args:
        articles: list of dicts from a scraper. Each must have at
                  minimum: source, url, headline.

    Returns:
        Dict with counts:
            articles_inserted, articles_updated,
            links_auto, links_thematic, links_preserved_manual
    """
    inserted        = 0
    updated         = 0
    links_auto      = 0
    links_thematic  = 0
    preserved_manual = 0

    conn = get_connection()
    try:
        for art in articles:
            # 1. Upsert the article (preserve ai_summary if it exists).
            existing = conn.execute(
                "SELECT id, ai_summary FROM news_articles WHERE url = ?",
                (art["url"],),
            ).fetchone()

            if existing is None:
                # Fresh insert.
                cursor = conn.execute(
                    """
                    INSERT INTO news_articles
                        (source, url, headline, snippet, published_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        art.get("source", "unknown"),
                        art["url"],
                        art["headline"],
                        art.get("snippet"),
                        art.get("published_at"),
                    ),
                )
                article_id = cursor.lastrowid
                inserted += 1
            else:
                # Update headline/snippet, preserve ai_summary.
                article_id = existing["id"]
                conn.execute(
                    """
                    UPDATE news_articles
                    SET headline     = ?,
                        snippet      = ?,
                        published_at = ?
                    WHERE id = ?
                    """,
                    (
                        art["headline"],
                        art.get("snippet"),
                        art.get("published_at"),
                        article_id,
                    ),
                )
                updated += 1

            # 2. Count manual links we'll preserve, then delete auto+thematic.
            manual_count = conn.execute(
                "SELECT COUNT(*) AS n FROM news_stock_links "
                "WHERE article_id = ? AND source = 'manual'",
                (article_id,),
            ).fetchone()["n"]
            preserved_manual += manual_count

            conn.execute(
                "DELETE FROM news_stock_links "
                "WHERE article_id = ? AND source IN ('auto', 'thematic')",
                (article_id,),
            )

            # Build symbol -> stock_id map for the stocks we care about.
            stock_symbols_needed: set = set()
            for s in art.get("matched_stocks", []):
                stock_symbols_needed.add(s)
            for theme in art.get("matched_themes", []):
                for s in theme["affected_stocks"]:
                    stock_symbols_needed.add(s)
            if not stock_symbols_needed:
                continue

            placeholders = ",".join("?" * len(stock_symbols_needed))
            rows = conn.execute(
                f"SELECT id, symbol FROM stocks WHERE symbol IN ({placeholders})",
                tuple(stock_symbols_needed),
            ).fetchall()
            symbol_to_id = {r["symbol"]: r["id"] for r in rows}

            # 3. Insert AUTO links (direct stock mentions).
            for symbol in art.get("matched_stocks", []):
                stock_id = symbol_to_id.get(symbol)
                if stock_id is None:
                    continue  # symbol not in DB (shouldn't happen — we validated)
                # Find which keyword phrase triggered the match (for debug).
                phrases = STOCK_KEYWORDS.get(symbol, [])
                text = (
                    (art.get("headline") or "") + " " +
                    (art.get("snippet") or "")
                ).lower()
                matched_phrase = next(
                    (p for p in sorted(phrases, key=len, reverse=True)
                     if p.lower() in text),
                    None,
                )

                conn.execute(
                    """
                    INSERT OR IGNORE INTO news_stock_links
                        (article_id, stock_id, source, confidence, matched_keyword)
                    VALUES (?, ?, 'auto', 1.0, ?)
                    """,
                    (article_id, stock_id, matched_phrase),
                )
                links_auto += 1

            # 4. Insert THEMATIC links.
            for theme in art.get("matched_themes", []):
                kw_str = ", ".join(theme["matched_keywords"][:3])
                for symbol in theme["affected_stocks"]:
                    stock_id = symbol_to_id.get(symbol)
                    if stock_id is None:
                        continue
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO news_stock_links
                            (article_id, stock_id, source, confidence, matched_keyword)
                        VALUES (?, ?, 'thematic', 0.5, ?)
                        """,
                        (article_id, stock_id, f"theme={theme['name']} kw={kw_str}"),
                    )
                    links_thematic += 1

        conn.commit()
    finally:
        conn.close()

    log.info(
        "Saved articles: %d inserted, %d updated. Links: %d auto, %d thematic, %d manual preserved.",
        inserted, updated, links_auto, links_thematic, preserved_manual,
    )
    return {
        "articles_inserted":       inserted,
        "articles_updated":        updated,
        "links_auto":              links_auto,
        "links_thematic":          links_thematic,
        "links_preserved_manual":  preserved_manual,
    }