"""
JSEdge - News scraper for Jamaica Observer business section.

Fetches the latest articles from jamaicaobserver.com/business/, parses
them into structured dicts, and filters out non-business content via
the site's own category classification.

Scope:
    - Only the FRONT page of /business/ per scrape - we run daily so
      we always get the newest articles. We don't crawl history.

Structure (as of May 2026):
    Each article is in an <article> tag with:
        - ta_permalink attribute: the article URL
        - div.categories: section label ("Business", "Sports", etc.)
        - div.title a: headline
        - div.subtitle: snippet/teaser text
        - div.date_part: publication date string

    The Observer page mixes business articles with carousel and sidebar
    items from other sections. We filter to only div.categories == "Business".

Politeness:
    - Custom User-Agent identifying us as a research tool
    - Respects HTTP error codes
"""

import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

from app.news.relevance import article_relevance
from app.news.enrichment import enrich_article_snippets, extract_observer_body

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OBSERVER_BUSINESS_URL = "https://www.jamaicaobserver.com/business/"

USER_AGENT = (
    "JSEdgeBot/0.1 (Jamaica Stock Exchange research tool; "
    "github.com/shavon195/jsedge)"
)

REQUEST_TIMEOUT = 15  # seconds


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
def fetch_business_page(url: str = OBSERVER_BUSINESS_URL) -> Optional[str]:
    """
    Fetch the raw HTML of the Observer business landing page.

    Returns:
        HTML string on success, None on failure.
    """
    headers = {"User-Agent": USER_AGENT}
    try:
        log.info("Fetching %s", url)
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        log.info("  -> %d bytes, status %d", len(resp.text), resp.status_code)
        return resp.text
    except requests.RequestException as e:
        log.error("Failed to fetch %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------
def parse_article_cards(html: str) -> list[dict]:
    """
    Parse the Observer business landing page HTML into article dicts.

    Each <article> tag on the page is examined. We KEEP articles where:
        - div.categories text is exactly "Business" (case-insensitive)

    We SKIP everything else (sports, entertainment, sidebar widgets,
    carousel items, etc.).

    Returns:
        List of dicts with keys: headline, url, snippet, published_at.
        Empty list if parsing finds nothing.
    """
    soup = BeautifulSoup(html, "lxml")
    cards: list[dict] = []
    skipped_non_business = 0

    for art in soup.find_all("article"):
        # --- Filter: must be in the Business category ---
        cat_el = art.select_one("div.categories")
        category = cat_el.get_text(strip=True) if cat_el else ""
        if category.lower() != "business":
            skipped_non_business += 1
            continue

        # --- URL: ta_permalink attribute on the <article> tag ---
        url = (art.get("ta_permalink") or "").strip()
        if not url:
            # Fallback: <a> tag inside div.title
            a = art.select_one("div.title a[href]")
            if a:
                url = a["href"].strip()
        if not url:
            continue

        # --- Headline: text of <a> inside div.title ---
        headline = None
        title_a = art.select_one("div.title a")
        if title_a:
            headline = title_a.get_text(strip=True)
        if not headline:
            # Fallback: any text in div.title
            title_el = art.select_one("div.title")
            if title_el:
                headline = title_el.get_text(strip=True)
        if not headline:
            continue

        # --- Snippet: text of div.subtitle ---
        snippet = None
        subtitle_el = art.select_one("div.subtitle")
        if subtitle_el:
            snippet = subtitle_el.get_text(strip=True) or None

        # --- Date: text of div.date_part ---
        published_at = None
        date_el = art.select_one("div.date_part")
        if date_el:
            published_at = date_el.get_text(strip=True) or None

        cards.append({
            "headline":     headline,
            "url":          url,
            "snippet":      snippet,
            "published_at": published_at,
        })

    log.info(
        "Parsed %d business article cards (skipped %d non-business).",
        len(cards), skipped_non_business,
    )
    return cards


# ---------------------------------------------------------------------------
# Top-level driver - fetch, parse, filter
# ---------------------------------------------------------------------------
def scrape_observer_business() -> list[dict]:
    """
    Full pipeline: fetch the Observer business page, parse articles,
    filter for relevance, and return only the relevant ones.

    Each returned dict has the article fields PLUS:
        - source = "observer"
        - matched_stocks (list[str])
        - matched_themes (list[dict])
        - matched_macros (list[str])

    Returns:
        List of relevant article dicts.
    """
    html = fetch_business_page()
    if html is None:
        return []

    articles = parse_article_cards(html)
    if not articles:
        log.warning("No business articles parsed - Observer HTML may have changed.")
        return []

    # Enrich thin/empty snippets by fetching article bodies.
    # Observer landing-page cards often have no subtitle, which leaves
    # the relevance filter very little text to match against.
    log.info("Enriching snippets via article body fetches...")
    enrich_article_snippets(articles, extractor=extract_observer_body)

    relevant: list[dict] = []
    skipped = 0

    for art in articles:
        rel = article_relevance(art)
        if rel["relevant"]:
            art["source"]         = "observer"
            art["matched_stocks"] = rel["matched_stocks"]
            art["matched_themes"] = rel["matched_themes"]
            art["matched_macros"] = rel["matched_macros"]
            relevant.append(art)
        else:
            skipped += 1
            log.debug("  Skipped: %s - %s", art["headline"][:60], rel["reason"])

    log.info(
        "Scraped %d business articles, kept %d relevant, skipped %d non-JSE.",
        len(articles), len(relevant), skipped,
    )
    return relevant