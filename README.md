# JSEdge 📈

> Long-term investment intelligence for the Jamaica Stock Exchange.

JSEdge is a web app that ranks every stock on the JSE main and junior markets by a composite "buy attractiveness" score, sends WhatsApp alerts when watched stocks hit your target limit prices, and builds a historical database that grows past JSE's public 1-year display limit.

## Status

🚧 **Phase 1 — In Development** 🚧

- [x] Project skeleton
- [x] SQLite schema + setup
- [ ] JSE daily scraper
- [ ] Ranking engine
- [ ] Web dashboard
- [ ] Manual fundamentals entry form
- [ ] Watchlist + limit price alerts
- [ ] WhatsApp + email alerts
- [ ] Live deployment
- [ ] News tab (Phase 2)
- [ ] Trading tab (Phase 3)

## Why This Exists

The Jamaica Stock Exchange offers limited public data tooling — only 1 year of price history, no ranking by valuation, no alerting. JSEdge fills those gaps with a system that scrapes daily, builds a permanent local record, and surfaces fundamentally attractive long-term opportunities.

## Tech Stack

- **Backend:** Python, FastAPI, SQLite
- **Frontend:** Jinja2 templates, HTMX, Tailwind CSS, Chart.js
- **Scraping:** Requests, BeautifulSoup
- **Scheduling:** GitHub Actions
- **Alerts:** Twilio (WhatsApp), Resend (email)
- **Hosting:** Railway / Render

## Architecture

```
JSE website  →  Daily scraper  →  SQLite DB  →  FastAPI  →  Web UI
                                       ↓
                                Ranking engine
                                       ↓
                                  Alert system  →  WhatsApp / Email
```

## Disclaimer

JSEdge is a personal research and learning tool. Nothing in this app is financial advice. All investment decisions are your own.

## Built By

Shavon Lloyd — engineering portfolio project, 2026.