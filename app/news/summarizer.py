"""
JSEdge - Article summarization via Gemini API.

Generates 2-3 sentence summaries of news articles with a JSE-investor
angle: what happened, why it matters for the linked stocks, and any
notable financial impact.

API key is loaded from user_settings table (key='gemini_api_key').
Summaries are saved to news_articles.ai_summary and timestamped via
news_articles.ai_summary_at.

Cost model:
    - Manual trigger only (Q1=C): user clicks "Summarize" on each article
    - Snippet-first, body-fetch fallback when snippet is thin (Q3)
    - JSE-investor angled prompt (Q2=B)
"""

import logging
from typing import Optional

from google import genai

from app.database import get_connection
from app.news.enrichment import fetch_article_html, extract_observer_body

log = logging.getLogger(__name__)


# Model selection: gemini-2.5-flash is cheap, fast, and plenty capable
# for a 2-3 sentence summary. Free tier covers ~1500 requests/day.
GEMINI_MODEL = "gemini-2.5-flash"

# If the snippet is shorter than this, fetch the article body to give
# Gemini more context. Same threshold as enrichment.MIN_USEFUL_LEN.
MIN_SNIPPET_LEN_FOR_SUMMARY = 120


def _load_api_key() -> Optional[str]:
    """Fetch the Gemini API key from user_settings. Returns None if unset."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM user_settings WHERE key = 'gemini_api_key'"
        ).fetchone()
        if row is None:
            return None
        val = (row["value"] or "").strip()
        return val or None
    finally:
        conn.close()


def _load_article_context(article_id: int) -> Optional[dict]:
    """
    Load the article + its active stock tags. Returns None if not found.

    Result shape:
        {
            "id": int, "source": str, "url": str,
            "headline": str, "snippet": str | None,
            "tags": [{"symbol": str, "name": str, "source": str}, ...]
        }
    """
    conn = get_connection()
    try:
        art = conn.execute(
            """
            SELECT id, source, url, headline, snippet
            FROM news_articles
            WHERE id = ?
            """,
            (article_id,),
        ).fetchone()
        if art is None:
            return None

        tags = conn.execute(
            """
            SELECT s.symbol AS symbol, s.name AS name, l.source AS source
            FROM news_stock_links l
            JOIN stocks s ON s.id = l.stock_id
            WHERE l.article_id = ? AND l.removed_at IS NULL
            ORDER BY
                CASE l.source
                    WHEN 'manual'   THEN 1
                    WHEN 'auto'     THEN 2
                    WHEN 'thematic' THEN 3
                    ELSE 4
                END,
                s.symbol
            """,
            (article_id,),
        ).fetchall()

        return {
            "id":       art["id"],
            "source":   art["source"],
            "url":      art["url"],
            "headline": art["headline"],
            "snippet":  art["snippet"],
            "tags":     [
                {"symbol": t["symbol"], "name": t["name"], "source": t["source"]}
                for t in tags
            ],
        }
    finally:
        conn.close()


def _ensure_enough_context(art: dict) -> str:
    """
    Return the best available text for the article: snippet if it's
    long enough, otherwise fetch the body and use that.

    Returns a string (possibly empty if everything failed).
    """
    snippet = art.get("snippet") or ""
    if len(snippet) >= MIN_SNIPPET_LEN_FOR_SUMMARY:
        return snippet

    # Snippet is thin — fetch body. Currently only Observer's extractor
    # is implemented; for Gleaner we fall back to the snippet alone since
    # Gleaner snippets are usually richer to begin with.
    url = art.get("url") or ""
    if not url:
        return snippet

    log.info("Snippet too short (%d chars); fetching body for %s", len(snippet), url)
    html = fetch_article_html(url)
    if html is None:
        return snippet

    body = extract_observer_body(html) or ""
    if body:
        # Combine: snippet first (it's editorially curated), then body.
        if snippet:
            return snippet + " " + body
        return body
    return snippet


def _build_prompt(art: dict, body_text: str) -> str:
    """
    Build the JSE-investor-angled prompt sent to Gemini.

    The prompt is firm about:
        - audience (JSE retail investor)
        - format (2-3 sentences)
        - angle (impact on tagged stocks)
        - tone (factual, not promotional)
    """
    tag_lines = []
    for t in art["tags"]:
        label = f"{t['symbol']} ({t['name']})"
        if t["source"] == "thematic":
            label += " [thematic link]"
        elif t["source"] == "manual":
            label += " [manually tagged]"
        tag_lines.append(f"  - {label}")
    tag_block = "\n".join(tag_lines) if tag_lines else "  (no stocks tagged)"

    return f"""You are a financial analyst writing for retail investors on the Jamaica Stock Exchange (JSE).

Summarize the following news article in 2-3 sentences. Focus on:
  1. What concretely happened (numbers, dates, parties).
  2. Why it matters to JSE investors holding or considering the tagged stocks.
  3. Any direct financial impact (earnings, dividends, regulatory action, etc.).

Do NOT speculate beyond the article. Do NOT use phrases like "investors should consider" or
"this could potentially". Stick to what the article actually says.

ARTICLE HEADLINE:
{art['headline']}

ARTICLE BODY:
{body_text or '(no body available)'}

TAGGED STOCKS:
{tag_block}

Now write the 2-3 sentence summary. Plain text only, no markdown, no bullet points."""


def summarize_article(article_id: int) -> dict:
    """
    Summarize a single article and save the result to news_articles.ai_summary.

    Returns a dict with:
        {
            "ok": bool,
            "summary": str | None,
            "error": str | None,
        }
    """
    api_key = _load_api_key()
    if api_key is None:
        return {"ok": False, "summary": None,
                "error": "Gemini API key not configured. Run: "
                         "python scripts/set_api_key.py gemini_api_key"}

    art = _load_article_context(article_id)
    if art is None:
        return {"ok": False, "summary": None,
                "error": f"Article {article_id} not found."}

    body_text = _ensure_enough_context(art)
    if not body_text.strip():
        return {"ok": False, "summary": None,
                "error": "No usable text content for this article."}

    prompt = _build_prompt(art, body_text)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        summary = (response.text or "").strip()
    except Exception as e:
        log.exception("Gemini API call failed for article %d", article_id)
        return {"ok": False, "summary": None,
                "error": f"Gemini call failed: {e}"}

    if not summary:
        return {"ok": False, "summary": None,
                "error": "Gemini returned an empty summary."}

    # Persist.
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE news_articles
            SET ai_summary    = ?,
                ai_summary_at = datetime('now')
            WHERE id = ?
            """,
            (summary, article_id),
        )
        conn.commit()
    finally:
        conn.close()

    log.info("Summary saved for article %d (%d chars).", article_id, len(summary))
    return {"ok": True, "summary": summary, "error": None}