"""
JSEdge — News keyword dictionary.

Maps each JSE stock symbol to alternative names/phrases that might
appear in news articles. Used by the auto-tagger to associate
scraped articles with relevant stocks.

ADDING A NEW KEYWORD
--------------------
When you spot an article that should have been tagged to a stock but
wasn't, add the phrase that should have triggered the match here.
Then re-run the tagger on existing articles.

DESIGN NOTES
------------
- Keywords are case-insensitive (lowercased before matching)
- Longest match wins — "NCB Financial Group" matches before "NCB"
- We focus on the most-traded ~20 stocks
- Ticker symbols are included ONLY when they are 5+ characters and
  unambiguous (NCBFG, JMMBGL, WISYNCO, FOSRICH, MPCCEL, FIRSTROCK).
  Short tickers (CAR, GK, SJ, BIL, etc.) are too risky — they would
  match unrelated words in article text.
- All symbols here have been verified against the stocks table.
"""

# Mapping: symbol -> list of recognition phrases
STOCK_KEYWORDS = {
    # ===== Big banks / financial conglomerates =====
    "NCBFG": [
        "NCB Financial Group",
        "National Commercial Bank Jamaica",
        "National Commercial Bank",
        "NCBFG",
    ],
    "JMMBGL": [
        "JMMB Group",
        "Jamaica Money Market Brokers",
        "JMMBGL",
    ],
    "SJ": [
        "Sagicor Group Jamaica",
        "Sagicor Jamaica",
    ],
    "SGJ": [
        "Scotia Group Jamaica",
        "Scotiabank Jamaica",
    ],
    "BIL": [
        "Barita Investments",
    ],
    "MGL": [
        "Mayberry Group",
    ],
    "MJE": [
        "Mayberry Jamaican Equities",
    ],

    # ===== Consumer staples / beverages / tobacco =====
    "CAR": [
        "Carreras Limited",
        "Carreras",
    ],
    "WISYNCO": [
        "Wisynco Group",
        "Wisynco",
        "WISYNCO",
    ],
    "GK": [
        "GraceKennedy Limited",
        "GraceKennedy",
        "Grace Kennedy",
    ],
    "JBG": [
        "Jamaica Broilers Group",
        "Jamaica Broilers",
    ],
    "LASD": [
        "Lasco Distributors",
    ],
    "LASM": [
        "Lasco Manufacturing",
    ],
    "LASF": [
        "Lasco Financial Services",
        "Lasco Financial",
    ],
    "SALF": [
        "Salada Foods Jamaica",
        "Salada Foods",
    ],

    # ===== Utilities / infrastructure =====
    "TJH": [
        "TransJamaica Highway",
        "Trans Jamaica Highway",
    ],

    # ===== Real estate / hospitality / tourism =====
    "DCOVE": [
        "Dolphin Cove Limited",
        "Dolphin Cove",
    ],
    "MPCCEL": [
        "MPC Caribbean Clean Energy",
        "MPCCEL",
    ],
    "PJX": [
        "Portland JSX",
    ],
    "FIRSTROCKJMD": [
        "First Rock Real Estate Investments",
        "First Rock Capital",
        "First Rock",
        "FIRSTROCK",
    ],

    # ===== Manufacturing / industrials =====
    "BRG": [
        "Berger Paints Jamaica",
        "Berger Paints",
    ],
    "FOSRICH": [
        "FosRich Company",
        "FosRich",
        "FOSRICH",
    ],
    "JAMT": [
        "Jamaican Teas",
    ],

    # ===== Other =====
    "JSE": [
        "Jamaica Stock Exchange",
    ],
    "SVL": [
        "Supreme Ventures Limited",
        "Supreme Ventures",
    ],
}


def get_all_keywords() -> dict:
    """Returns the keyword dictionary."""
    return STOCK_KEYWORDS


def total_keywords() -> int:
    """Count of total keyword phrases across all stocks."""
    return sum(len(v) for v in STOCK_KEYWORDS.values())


def total_stocks_with_keywords() -> int:
    """Count of stocks that have at least one keyword."""
    return len(STOCK_KEYWORDS)