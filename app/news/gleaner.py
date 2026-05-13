"""
JSEdge — News scraper for Jamaica Gleaner business section.

Fetches the latest articles from jamaica-gleaner.com/business, parses
them into structured dicts, and filters out international noise via
the shared relevance module.

Scope:
    - Only the FRONT page (page 1) of /business per scrape — we run
      daily so we always get the newest articles. We don't crawl 86
      pages of history.

Politeness:
    - Custom User-Agent identifying us as a research tool
    - 1-second delay between page fetches (we only fetch one page anyway)
    - Respects HTTP error codes
"""

import logging
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.news.relevance import article_relevance

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
# Top-level driver — fetch, parse, filter
# ---------------------------------------------------------------------------
def scrape_gleaner_business() -> list[dict]:
    """
    Full pipeline: fetch the Gleaner business page, parse articles,
    filter for relevance, and return only the relevant ones.

    Each returned dict has the article fields PLUS:
        - source = "gleaner"
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
        log.warning("No articles parsed — Gleaner HTML structure may have changed.")
        return []

    relevant: list[dict] = []
    skipped = 0

    for art in articles:
        rel = article_relevance(art)
        if rel["relevant"]:
            art["source"]         = "gleaner"
            art["matched_stocks"] = rel["matched_stocks"]
            art["matched_themes"] = rel["matched_themes"]
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