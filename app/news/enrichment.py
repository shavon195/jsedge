"""
JSEdge - News article body enrichment.

For sources whose landing-page cards have empty or thin snippets
(notably the Jamaica Observer), we can optionally fetch the full
article page and extract the lead paragraphs to use as a snippet.

This gives the relevance filter (article_relevance) much more text
to match against, dramatically improving JSE keyword hits.

POLITENESS
----------
- 1-second delay between fetches (configurable)
- Custom User-Agent identifying us as a research tool
- Errors are logged and swallowed - one bad URL never breaks the batch
- Skips articles whose snippet is already long enough (MIN_USEFUL_LEN)

DESIGN
------
- enrich_article_snippets() takes a list of article dicts and mutates
  them in place, only filling 'snippet' where it's missing/too short.
- The fetch + extract is source-aware: pass a parser function tailored
  to that source's article HTML (lead-paragraph selector).
"""

import logging
import time
from typing import Callable, Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)


USER_AGENT = (
    "JSEdgeBot/0.1 (Jamaica Stock Exchange research tool; "
    "github.com/shavon195/jsedge)"
)
REQUEST_TIMEOUT = 15   # seconds
REQUEST_DELAY   = 1.0  # seconds between fetches (politeness)
MIN_USEFUL_LEN  = 60   # snippet shorter than this triggers a body fetch
MAX_SNIPPET_LEN = 600  # truncate enriched snippets to this many chars


def fetch_article_html(url: str) -> Optional[str]:
    """
    Fetch the raw HTML of a single article page.

    Returns:
        HTML string on success, None on failure.
    """
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        log.warning("Body fetch failed for %s: %s", url, e)
        return None


def extract_observer_body(html: str) -> Optional[str]:
    """
    Extract lead paragraphs from a Jamaica Observer article page.

    The Observer wraps article body text in <div class="article-content">
    or similar - we scan for paragraph tags inside the main content area
    and concatenate the first few that look like real prose.

    Returns:
        Concatenated lead text on success, None if nothing usable found.
    """
    soup = BeautifulSoup(html, "lxml")

    # Try several known Observer body containers in order of preference.
    candidates = [
        "div.article-content",
        "div.entry-content",
        "div.post-content",
        "article",
    ]

    body_el = None
    for sel in candidates:
        body_el = soup.select_one(sel)
        if body_el:
            break

    if body_el is None:
        # Last resort: just look at the whole page.
        body_el = soup

    # Collect text from <p> tags that look like real prose
    # (length > 40 chars), skipping share/credit/byline boilerplate.
    paragraphs: list[str] = []
    boilerplate_markers = (
        "share this",
        "follow us",
        "subscribe",
        "click here",
        "loading...",
        "©",
        "all rights reserved",
    )
    for p in body_el.find_all("p"):
        txt = p.get_text(separator=" ", strip=True)
        if len(txt) < 40:
            continue
        lower = txt.lower()
        if any(marker in lower for marker in boilerplate_markers):
            continue
        paragraphs.append(txt)
        if len(paragraphs) >= 3:
            break

    if not paragraphs:
        return None

    combined = " ".join(paragraphs)
    if len(combined) > MAX_SNIPPET_LEN:
        combined = combined[:MAX_SNIPPET_LEN].rsplit(" ", 1)[0] + "..."
    return combined


def enrich_article_snippets(
    articles: list[dict],
    extractor: Callable[[str], Optional[str]],
    delay: float = REQUEST_DELAY,
) -> dict:
    """
    Fill in missing/thin snippets by fetching each article's body page.

    For each article in the list:
        - If the existing snippet is at least MIN_USEFUL_LEN chars, skip.
        - Otherwise, fetch the article page, run the source-specific
          extractor, and assign the result to art['snippet'].
        - Sleep `delay` seconds between fetches.

    Args:
        articles:  list of article dicts (will be mutated in place).
        extractor: function(html_str) -> snippet_str_or_None,
                   appropriate for the article source.
        delay:     seconds to wait between consecutive fetches.

    Returns:
        Dict with counts: enriched, skipped, failed.
    """
    enriched = 0
    skipped  = 0
    failed   = 0

    for i, art in enumerate(articles):
        existing = art.get("snippet") or ""
        if len(existing) >= MIN_USEFUL_LEN:
            skipped += 1
            continue

        url = art.get("url")
        if not url:
            failed += 1
            continue

        # Politeness delay (but not before the first fetch).
        if i > 0 and (enriched + failed) > 0:
            time.sleep(delay)

        html = fetch_article_html(url)
        if html is None:
            failed += 1
            continue

        body = extractor(html)
        if not body:
            failed += 1
            continue

        # Preserve any existing short snippet by prepending it.
        if existing:
            art["snippet"] = existing + " " + body
        else:
            art["snippet"] = body
        enriched += 1

    log.info(
        "Enrichment complete: %d enriched, %d skipped (already had snippet), %d failed.",
        enriched, skipped, failed,
    )
    return {"enriched": enriched, "skipped": skipped, "failed": failed}