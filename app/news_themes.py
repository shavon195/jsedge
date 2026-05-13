"""
JSEdge — News themes (macro topic → affected stocks).

Themes capture macro factors that affect JSE stocks even when an article
doesn't mention any company by name. For example:

    Article: "OPEC announces oil production cuts"
    No JSE stock is named, but this affects:
        - WISYNCO  (manufacturing energy costs)
        - JBG      (poultry feed transportation)
        - TJH      (toll revenue tied to driving habits)

Each theme has:
    keywords:         phrases that identify the topic in news text
    affected_stocks:  JSE symbols this theme affects
    description:      human-readable summary (shown in UI later)

DESIGN
------
- Themes are LOWER confidence than direct stock mentions. The UI/ranking
  treats them as supplementary signals, not primary.
- An article can match MULTIPLE themes (Q2 = A). Each theme contributes
  its full list of affected stocks.
- If an article ALSO has a direct stock mention, the thematic link is
  suppressed for that stock (Q3 = A) — direct beats thematic.
"""

# Mapping: theme name -> {keywords, affected_stocks, description}
THEMES = {
    "tourism": {
        "description": (
            "Caribbean tourism, airline routes, visitor arrivals, "
            "resorts and cruises. Drives demand for hospitality, "
            "transport, and food/beverage to tourists."
        ),
        "keywords": [
            "Spirit Airlines",
            "Caribbean Airlines",
            "JetBlue",
            "American Airlines Jamaica",
            "Air Jamaica",
            "visitor arrivals",
            "tourism Jamaica",
            "Jamaica tourism",
            "cruise ship",
            "cruise passengers",
            "all-inclusive resort",
            "Sandals Resorts",
            "Couples Resorts",
            "Half Moon",
            "tourist arrivals",
            "Jamaica Tourist Board",
            "JTB",
        ],
        "affected_stocks": ["DCOVE", "JBG"],
    },

    "oil_energy": {
        "description": (
            "Oil and fuel prices, OPEC decisions, refinery output. "
            "Affects manufacturing input costs, logistics fleets, and "
            "general inflation."
        ),
        "keywords": [
            "OPEC",
            "OPEC+",
            "crude oil",
            "oil prices",
            "Brent crude",
            "WTI crude",
            "petroleum prices",
            "fuel prices",
            "gasoline prices",
            "diesel prices",
            "oil production cut",
            "Petrojam",
            "energy costs",
        ],
        "affected_stocks": ["WISYNCO", "JBG", "TJH"],
    },

    "usd_jmd": {
        "description": (
            "USD/JMD exchange rate and Jamaican dollar movements. "
            "Affects every importer's input costs and every exporter's "
            "revenue translation."
        ),
        "keywords": [
            "Jamaican dollar",
            "JMD",
            "USD JMD",
            "USD/JMD",
            "exchange rate Jamaica",
            "Jamaican dollar depreciation",
            "Jamaican dollar appreciation",
            "weighted average selling rate",
            "WASR",
            "Bank of Jamaica intervention",
            "currency depreciation",
            "currency appreciation",
        ],
        "affected_stocks": ["WISYNCO", "GK", "LASD", "JBG", "CAR"],
    },

    "interest_rates": {
        "description": (
            "Bank of Jamaica policy rate, US Federal Reserve decisions, "
            "and bond yields. Affects bank net interest margins and "
            "investor demand for equities vs. fixed income."
        ),
        "keywords": [
            "Bank of Jamaica policy rate",
            "BOJ rate",
            "BOJ policy",
            "BOJ Monetary Policy Committee",
            "interest rate hike",
            "interest rate cut",
            "rate decision",
            "Federal Reserve",
            "Fed rate",
            "Fed funds rate",
            "Jerome Powell",
            "FOMC",
            "Treasury yields",
            "bond yields",
            "yield curve",
        ],
        "affected_stocks": ["NCBFG", "JMMBGL", "SJ", "SGJ", "BIL", "MGL"],
    },

    "insurance_sector": {
        "description": (
            "Insurance regulation, hurricane claims, reinsurance pricing. "
            "Hurricane seasons matter especially — claims hit insurers "
            "while reinsurance cost spikes hit profitability."
        ),
        "keywords": [
            "insurance industry",
            "insurance regulation",
            "insurance tax",
            "insurance company Jamaica",
            "hurricane claims",
            "reinsurance",
            "insurance premiums",
            "Financial Services Commission insurance",
            "insurance sector Jamaica",
            "FSC insurance",
            "natural disaster insurance",
        ],
        "affected_stocks": ["SJ"],
    },

    "distribution_retail": {
        "description": (
            "Retail and wholesale distribution sector. Competitor news, "
            "M&A activity, and supply chain shifts in food/consumer goods "
            "distribution affect the major players."
        ),
        "keywords": [
            "Massy Holdings",
            "Massy distribution",
            "Massy Jamaica",
            "PriceSmart",
            "MegaMart",
            "Hi-Lo",
            "Loshusan",
            "supermarket chain Jamaica",
            "wholesale distribution Jamaica",
            "retail sector Jamaica",
            "consumer goods distribution",
        ],
        "affected_stocks": ["GK", "LASD", "WISYNCO"],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_all_themes() -> dict:
    """Returns the themes dictionary."""
    return THEMES


def total_themes() -> int:
    """Count of themes defined."""
    return len(THEMES)


def total_theme_keywords() -> int:
    """Total keyword phrases across all themes."""
    return sum(len(t["keywords"]) for t in THEMES.values())


def stocks_affected_by_themes() -> set:
    """Set of all stock symbols referenced by any theme."""
    result = set()
    for theme in THEMES.values():
        result.update(theme["affected_stocks"])
    return result