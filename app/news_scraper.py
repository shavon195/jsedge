"""
JSEdge — News scraper for Jamaica Gleaner business section.

Fetches the latest articles from jamaica-gleaner.com/business, parses
them into structured dicts, and filters out international noise.

Scope:
    - Only the FRONT page (page 1) of /business per scrape — we run
      daily so we always get the newest articles. We don't crawl 86
      pages of history.

Filter logic (Q1 = C, hybrid):
    KEEP if article matches at least one of:
        - A JSE stock keyword (from app.news_keywords.STOCK_KEYWORDS)
        - A Jamaica macro keyword (Bank of Jamaica, JSE Index, etc.)
    SKIP otherwise (international noise like Iran war, US Fed, etc.)

Politeness:
    - Custom User-Agent identifying us as a research tool
    - 1-second delay between page fetches (we only fetch one page anyway)
    - Respects HTTP error codes
"""

import logging
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.news_keywords import STOCK_KEYWORDS

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GLEANER_BUSINESS_URL = "https://jamaica-gleaner.com/business"

USER_AGENT = (
    "JSEdgeBot/0.1 (Jamaica Stock Exchange research tool; "
    "github.com/shavon195/jsedge)"
)

REQUEST_TIMEOUT = 15   # seconds
REQUEST_DELAY   = 1.0  # seconds between requests (politeness)

# Macro Jamaica keywords — keep articles mentioning these even if no
# specific JSE stock is named. Captures general market/economy news.
MACRO_KEYWORDS = [
    "Jamaica Stock Exchange",
    "JSE Index",
    "JSE Main Market",
    "JSE Junior Market",
    "Bank of Jamaica",
    "Financial Services Commission",
    "FSC Jamaica",
    "Ministry of Finance Jamaica",
    "Jamaican dollar",
    "Jamaica economy",
    "Jamaica inflation",
    "Planning Institute of Jamaica",
    "PIOJ",
    "STATIN",  # Statistical Institute of Jamaica
]


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
def fetch_business_page(url: str = GLEANER_BUSINESS_URL) -> Optional[str]:
    """
    Fetch the raw HTML of the Gleaner business landing page.

    Returns:
        HTML string on success, None on failure.
    """
    headers = {"User-Agent": USER_AGENT}
    try:
        log.info("Fetching %s", url)
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        log.info("  → %d bytes, status %d", len(resp.text), resp.status_code)
        return resp.text
    except requests.RequestException as e:
        log.error("Failed to fetch %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------
def parse_article_cards(html: str) -> list[dict]:
    """
    Parse the business landing page HTML into a list of article dicts.

    The Gleaner uses data-component="card" on each article card. Each
    card has:
        - Two <h2> tags — one decorative (aria-hidden=true), one real
        - A <p> containing the snippet (possibly nested in a <div>)
        - A date span inside `.card__content`
        - The article link in the "Read more" button or surrounding <a>

    Returns:
        List of dicts with keys: headline, url, snippet, published_at.
        Empty list if parsing finds nothing.
    """
    soup = BeautifulSoup(html, "lxml")
    cards: list[dict] = []

    for card in soup.select('[data-component="card"]'):
        # Headline — skip aria-hidden decorative ones, take the real <h2>.
        headline = None
        for h in card.select("h2, h3"):
            if h.get("aria-hidden") == "true":
                continue  # decorative overlay headline
            text = h.get_text(strip=True)
            if text:
                headline = text
                break
        # Fallback: if all <h2>s are aria-hidden, use the first one anyway.
        if not headline:
            h_any = card.select_one("h2, h3")
            if h_any:
                headline = h_any.get_text(strip=True)
        if not headline:
            continue

        # Link — find the <a> with an article URL. Prefer ones with
        # /article/ in the href (filters out menu/category links).
        url = None
        for link in card.select("a[href]"):
            href = link["href"].strip()
            if "/article/" in href:
                url = urljoin(GLEANER_BUSINESS_URL, href)
                break
        if not url:
            # Fallback: any link.
            any_link = card.select_one("a[href]")
            if any_link:
                url = urljoin(GLEANER_BUSINESS_URL, any_link["href"].strip())
        if not url:
            continue

        # Snippet — the Gleaner uses invalid HTML <p><div>...</div></p>,
        # which BeautifulSoup auto-corrects by splitting them into
        # sibling tags. So the text usually lives in the <div> that
        # immediately FOLLOWS the (now-empty) <p>.
        snippet = None
        p_el = card.select_one(".card__content p")
        if p_el:
            # First try: text actually inside the <p>.
            text = p_el.get_text(separator=" ", strip=True)
            if text:
                snippet = text
            else:
                # Auto-corrected case: look at the NEXT sibling <div>.
                next_div = p_el.find_next_sibling("div")
                if next_div:
                    snippet = next_div.get_text(separator=" ", strip=True)

        # Last-resort fallback: grab all text in .card__content,
        # minus the headline.
        if not snippet:
            content = card.select_one(".card__content")
            if content:
                all_text = content.get_text(separator=" ", strip=True)
                if headline and headline in all_text:
                    snippet = all_text.replace(headline, "", 1).strip()
                else:
                    snippet = all_text or None

        # Publish date — look in the .card__content header area.
        published_at = None
        # Try <time> tag first.
        date_el = card.select_one("time, [datetime]")
        if date_el:
            published_at = date_el.get("datetime") or date_el.get_text(strip=True)
        else:
            # The Gleaner uses a date <span> inside .card__content.
            date_span = card.select_one(".card__content span")
            if date_span:
                txt = date_span.get_text(strip=True)
                # Quick sanity check — should look like a date.
                if any(month in txt for month in [
                    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
                ]):
                    published_at = txt

        cards.append({
            "headline":     headline,
            "url":          url,
            "snippet":      snippet,
            "published_at": published_at,
        })

    log.info("Parsed %d article cards.", len(cards))
    return cards

# ---------------------------------------------------------------------------
# Relevance filter — Q1 = C hybrid
# ---------------------------------------------------------------------------
def article_relevance(article: dict) -> dict:
    """
    Decide whether an article is relevant and why.

    Checks the headline + snippet against:
        1. Stock keywords (STOCK_KEYWORDS) — direct mentions
        2. Theme keywords (THEMES) — macro topics that affect stocks
        3. Macro Jamaica keywords (MACRO_KEYWORDS) — general market news

    Application of Q3 = A: if a stock is already directly mentioned,
    we suppress thematic links to THAT stock (direct beats thematic).

    Returns:
        Dict with:
            relevant:       bool
            matched_stocks: list of stocks directly mentioned
            matched_themes: list of theme dicts:
                            {name, affected_stocks, matched_keywords}
            matched_macros: list of macro keywords matched
            reason:         human-readable explanation
    """
    from app.news_themes import THEMES

    text_parts = [article.get("headline") or "", article.get("snippet") or ""]
    text = " ".join(text_parts).lower()

    # --- 1. Direct stock keyword matching (longest-first) ---
    matched_stocks: list[str] = []
    for symbol, phrases in STOCK_KEYWORDS.items():
        for phrase in sorted(phrases, key=len, reverse=True):
            if phrase.lower() in text:
                matched_stocks.append(symbol)
                break

    # --- 2. Theme matching ---
    matched_themes: list[dict] = []
    for theme_name, theme_data in THEMES.items():
        matched_keywords = [
            kw for kw in theme_data["keywords"]
            if kw.lower() in text
        ]
        if matched_keywords:
            # Q3 = A: drop affected stocks that were already directly matched.
            thematic_stocks = [
                s for s in theme_data["affected_stocks"]
                if s not in matched_stocks
            ]
            matched_themes.append({
                "name":             theme_name,
                "affected_stocks":  thematic_stocks,
                "matched_keywords": matched_keywords,
            })

    # --- 3. Macro Jamaica keywords ---
    matched_macros = [m for m in MACRO_KEYWORDS if m.lower() in text]

    # Article is relevant if ANY of the three sources match.
    relevant = bool(matched_stocks or matched_themes or matched_macros)

    # Build a human-readable reason for the relevance.
    reasons = []
    if matched_stocks:
        reasons.append(f"stocks: {', '.join(matched_stocks)}")
    if matched_themes:
        theme_summary = ", ".join(
            f"{t['name']}→{','.join(t['affected_stocks']) or '(no new stocks)'}"
            for t in matched_themes
        )
        reasons.append(f"themes: {theme_summary}")
    if matched_macros:
        reasons.append(f"macros: {', '.join(matched_macros)}")

    reason = " | ".join(reasons) if reasons else (
        "no JSE/Jamaica keyword match — skipped as international"
    )

    return {
        "relevant":       relevant,
        "matched_stocks": matched_stocks,
        "matched_themes": matched_themes,
        "matched_macros": matched_macros,
        "reason":         reason,
    }
# ---------------------------------------------------------------------------
# Top-level driver — fetch, parse, filter
# ---------------------------------------------------------------------------
def scrape_gleaner_business() -> list[dict]:
    """
    Full pipeline: fetch the Gleaner business page, parse articles,
    filter for relevance, and return only the relevant ones.

    Each returned dict has the article fields PLUS:
        - matched_stocks (list[str])
        - matched_macros (list[str])
        - source = "gleaner"

    Returns:
        List of relevant article dicts.
    """
    html = fetch_business_page()
    if html is None:
        return []

    articles = parse_article_cards(html)
    if not articles:
        log.warning("No articles parsed — Gleaner HTML structure may have changed.")
        return []

    relevant: list[dict] = []
    skipped = 0

    for art in articles:
        rel = article_relevance(art)
        if rel["relevant"]:
            art["source"]         = "gleaner"
            art["matched_stocks"] = rel["matched_stocks"]
            art["matched_macros"] = rel["matched_macros"]
            relevant.append(art)
        else:
            skipped += 1
            log.debug("  Skipped: %s — %s", art["headline"][:60], rel["reason"])

    log.info(
        "Scraped %d articles, kept %d relevant, skipped %d international.",
        len(articles), len(relevant), skipped,
    )
    return relevant

# ---------------------------------------------------------------------------
# Persist to database
# ---------------------------------------------------------------------------
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
        articles: list of dicts from scrape_gleaner_business().
                  Each must have at minimum: source, url, headline.

    Returns:
        Dict with counts:
            articles_inserted, articles_updated,
            links_auto, links_thematic, links_preserved_manual
    """
    from app.database import get_connection
    from app.news_keywords import STOCK_KEYWORDS

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
                        art.get("source", "gleaner"),
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