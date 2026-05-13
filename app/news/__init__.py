"""
JSEdge — News module.

Public API for news scraping, relevance filtering, and DB persistence.
Import from here rather than the individual submodules:

    from app.news import (
        scrape_gleaner_business,
        save_articles_to_db,
        article_relevance,
    )
"""

from app.news.gleaner import (
    fetch_business_page  as fetch_gleaner_business_page,
    parse_article_cards  as parse_gleaner_article_cards,
    scrape_gleaner_business,
)
from app.news.observer import (
    fetch_business_page  as fetch_observer_business_page,
    parse_article_cards  as parse_observer_article_cards,
    scrape_observer_business,
)
from app.news.relevance import article_relevance, MACRO_KEYWORDS
from app.news.save import save_articles_to_db

__all__ = [
    "fetch_gleaner_business_page",
    "parse_gleaner_article_cards",
    "scrape_gleaner_business",
    "fetch_observer_business_page",
    "parse_observer_article_cards",
    "scrape_observer_business",
    "article_relevance",
    "MACRO_KEYWORDS",
    "save_articles_to_db",
]