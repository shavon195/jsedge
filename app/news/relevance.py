"""
JSEdge — News relevance filter (source-agnostic).

Decides whether a parsed article is relevant to JSE investors and tags
which stocks/themes/macros it matches. Used by every news source
(Gleaner, Observer, JSE filings, etc.) — the parsers produce article
dicts, this module decides what to keep and how to tag.

Filter logic (Q1 = C, hybrid):
    KEEP if article matches at least one of:
        - A JSE stock keyword (from app.news_keywords.STOCK_KEYWORDS)
        - A theme keyword (from app.news_themes.THEMES)
        - A Jamaica macro keyword (Bank of Jamaica, JSE Index, etc.)
    SKIP otherwise (international noise like Iran war, US Fed, etc.)

Q3 = A: if a stock is already directly mentioned in the article, we
suppress thematic links to THAT stock — direct beats thematic.
"""

from app.news_keywords import STOCK_KEYWORDS
from app.news_themes import THEMES


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