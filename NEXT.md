# JSEdge — Next Session

## 🎯 Quick-resume

```bash
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
# then open http://localhost:8000
```

## ✅ Done so far (28 commits)

**Foundation**
- FastAPI server with 3 tabs (JSE / News / Trading)
- SQLite schema with 11 tables (stocks, prices_daily, fundamentals, scores, watchlist, alerts_log, purchases, account_balance, user_settings, news_articles, news_stock_links)
- 101 stocks loaded (53 Main Market + 48 Junior)

**JSE Scraper**
- Static-HTML scraper with retry logic, empty-page detection, low-count warnings
- Idempotent saves via ON CONFLICT
- Daily run via `python scripts/run_scraper.py --offline --date 2026-04-28`

**Ranking engine — horizon-aware**
- 8 sub-scores: 4 technical (position, volume, dividend, range) + 4 fundamentals (ROE, FCF margin, debt, profit margin)
- 5 horizons: 6mo / 1yr / 2yr / 5yr / 10+yr — each with its own weight matrix
- Strict historical depth gating (3+ rows for 5yr, 5+ for 10yr)
- 75% data-completeness threshold for main ranking
- Multi-horizon storage in `scores` table (UNIQUE constraint includes horizon)
- Recompute via `python scripts/compute_all_horizons.py`

**Fundamentals data entry**
- Per-stock list page with progress bar + smart sort
- Add new period form (13 fields, browser + server validation)
- View / Edit / Delete with flash banners and danger-zone confirm
- Save & Add Another for fast chained entry
- Prev / Next stock navigation
- Real data entered: **CAR (Carreras Limited) FY2024** + **WISYNCO (Wisynco Group) FY2025**

**Dashboard**
- Horizon dropdown on JSE tab — switches between 6mo / 1yr / 2yr / 5yr / 10+yr
- Context-sensitive disclosure banners per horizon
- Default horizon: **10+ years** (decade portfolio is JSEdge's identity)
- Incomplete tier sorted by completeness first, then score

**News scraper — Session 1 of 3 (commit 3ed7281)**
- Jamaica Gleaner business section scraper
- Keyword dictionary: 23 JSE stocks, ~50 phrase variants (`app/news_keywords.py`)
- Themes system: 6 macro themes, ~80 keywords, 12 affected stocks (`app/news_themes.py`)
- Two-table DB schema: `news_articles` + `news_stock_links`
- Save pipeline with smart upsert and surgical link cleanup

**News scraper — Session 2 of 3 (commits e379645, b16f33d, 93bec3f, 8ce435b, 4777961)**
- Fixed `matched_themes` not being assigned in `scrape_gleaner_business()`
- Refactored `app/news_scraper.py` into clean `app/news/` package:
  - `relevance.py` (shared filter)
  - `save.py` (shared DB persistence)
  - `gleaner.py` (Gleaner-specific)
  - `observer.py` (Observer-specific, new)
  - `enrichment.py` (article-body fetcher for thin snippets)
  - `queries.py` (read/write helpers for /news page)
- **Jamaica Observer scraper:** filters by `div.categories == "Business"`, fetches article bodies to enrich thin snippets (1s delay between fetches), wired into daily pipeline alongside Gleaner
- **Keyword improvements:**
  - Added long-ticker variants (NCBFG, JMMBGL, WISYNCO, FOSRICH, MPCCEL)
  - Added FIRSTROCKJMD entry (was missing)
  - Fixed substring false positive (e.g. "STATIN" matching inside "stating") via regex word boundaries
- **`/news` page UI:**
  - Lists scraped articles with source badges (Gleaner amber, Observer cyan)
  - Color-coded tags by type (auto gray, thematic purple, manual emerald)
  - Soft-delete remove (× button) — `removed_at` column added via migration
  - Add manual tag (collapsible dropdown picker)
  - Soft-deletes survive re-scrapes (auto-tagger respects user removals)
  - Removing then re-adding restores the same row (no duplicates)

**Real-data results (May 13, 2026):**
- Gleaner: 10 parsed → 5 kept (3 auto links + 5 thematic links)
- Observer: 14 parsed → 5 kept after enrichment (5 auto links)
- Total daily: ~10 articles, ~9 auto + ~5 thematic links

---

## 🚧 TODO — in priority order

### 1. News Session 3 (~3-5 hours)
- **Gemini API integration** for AI summaries on each article
- **`/news` enhancements:** filtering by source/stock/theme, search, sort options
- **Per-stock news feed** — show all articles tagged to a single stock (linked from stock detail pages, future)
- Add a "Refresh news now" button on the /news page that triggers `scrape_news.py`

### 2. ⚠️ AUTH BEFORE DEPLOY (~75 min) — locked-in requirement
Password-protect admin pages (`/fundamentals/*` AND `/news/*/tags/*` write routes).
- Install `itsdangerous` + `python-dotenv`
- `.env` with `ADMIN_PASSWORD` and `SESSION_SECRET`
- Session middleware + signed cookies
- `/admin/login` and `/admin/logout` routes + login template
- `require_admin` decorator on all `/fundamentals/*` and `/news/.../remove` and `/news/.../add` routes
- Login indicator in top nav
- **Must be done BEFORE deploying to Render** — otherwise anyone on the internet can edit data and tags

### 3. Enter more fundamentals data (~6-13 hours, paced over weeks)
Goal: 80 companies of fundamentals data so the 5yr/10yr rankings come alive.

Done so far: CAR, WISYNCO.

Recommended next picks (non-bank, simple financials):
- GK (GraceKennedy)
- LASD (Lasco Distributors)
- DCOVE (Dolphin Cove)
- JBG (Jamaica Broilers)

Defer until non-bank pattern is solid:
- NCBFG, JMMBGL, BIL (banks have weird financials — deposits, lease quirks)

### 4. Watchlist + price alerts (~4-6 hours)
Schema already exists. Build:
- "Add to watchlist" button on stock pages
- Watchlist tab on JSE page
- Set limit prices per stock
- Trigger alerts when price hits the limit

### 5. WhatsApp + email alerts (~6-8 hours)
- Twilio (WhatsApp) integration
- Resend (email) integration
- User toggle: which alerts go where
- Daily summary at market close

### 6. Deploy to Render or Railway (~3-4 hours)
- **Auth (#2) must be done first**
- GitHub Actions for daily scrape
- Persistent SQLite or migrate to PostgreSQL
- Custom domain optional

### 7. Trading tab — Phase 3
- TradingView embed
- RSI / MACD / MA indicators
- Paper trading
- Backtesting against historical scores

### 8. Future — JSE filings scraper (~20+ hours)
Replace manual fundamentals entry with auto-extraction from JSE filings PDFs.
Defer until non-bank patterns are solid (5+ companies entered manually).

### 9. Tech debt
- `app/database.py` SCHEMA_SQL is missing `news_articles` and `news_stock_links` definitions — they were created out-of-band. Either reconstruct them in SCHEMA_SQL (matching what's in the live DB) or formalize the migration script approach. Note: `news_stock_links.removed_at` was added via `scripts/migrate_add_removed_at.py` and should also be reflected in SCHEMA_SQL once we reconcile.

---

## 📋 Verification commands

```bash
# Inspect database
python scripts/check_db.py

# Re-run scoring across all 5 horizons
python scripts/compute_all_horizons.py

# Test horizon ranking output
python scripts/test_horizon_ranking.py

# Run JSE scraper (offline against saved sample)
python scripts/run_scraper.py --offline --date 2026-04-28

# Run JSE scraper (live)
python scripts/run_scraper.py --date YYYY-MM-DD

# News scraper — full pipeline (Gleaner + Observer)
python scripts/scrape_news.py

# News debug — Gleaner only, with relevance decisions per article
python scripts/debug_news_scraper.py

# News debug — Observer only, with enrichment + relevance
python scripts/debug_observer_scraper.py

# Wipe both news tables (with confirmation prompt)
python scripts/wipe_news.py

# Inspect link history for a specific stock symbol (auto/thematic/manual + removed_at)
python scripts/check_tag.py NCBFG

# Look up a stock by name fragment to find its symbol
python scripts/find_stock.py first

# Schema migration: add removed_at column (idempotent)
python scripts/migrate_add_removed_at.py
```

---

## 📐 Design decisions (for future-me)

- **Numbers stored raw** (J$19,551,584,000 not abbreviated) — avoids unit confusion
- **Manual fundamentals entry, NOT AI extraction** — too high hallucination risk for financial numbers
- **Two-tier ranking** (main + incomplete) — same pattern across technical and fundamentals
- **Default horizon = 10_years** — JSEdge's identity is decade investing
- **Strong horizon weight differences** — short = technical, long = fundamentals (no overlap)
- **Strict historical depth** — long horizons require multi-year fundamentals
- **Option B for scoring storage** — pre-compute all 5 horizons
- **Operating income proxy = profit before tax** — when no clean operating income line exists

**News scraper design:**
- **Q1 hybrid filter** — keep articles with stock keywords OR macro Jamaica keywords; skip pure international
- **Q2 = B2 hybrid auto-tag with override** — auto-tags on scrape, manual corrections preserved across re-scrapes
- **Q3 = A Gemini** — for AI summaries when implemented (Session 3)
- **Q4 = C + D** — daily auto-refresh + manual button
- **Q5 = A SQLite** — same DB
- **Q6 = D combined feed** — featured + chronological + filters
- **Themes Q2 = A** — article can match multiple themes; tag all
- **Themes Q3 = A** — direct stock mention beats thematic link
- **Save Q1 = C** — re-scrape updates headline/snippet but preserves ai_summary
- **Save Q2 = C** — clear auto+thematic links on re-save, preserve manual links

**News scraper design (Session 2 additions):**
- **Per-source modules under `app/news/`** — Gleaner and Observer are peers; shared logic (relevance, save, enrichment) lives in its own file. Adding a third source = drop in a new module, no refactor needed.
- **Observer business filter** — use `div.categories == "Business"` from the page's own DOM, not parent-slot inspection or URL inspection. Resilient to layout reshuffles.
- **Body enrichment, not just card snippets** — Observer cards often have no subtitle; we fetch the article URL and extract first paragraphs. 1s delay between fetches; skips articles that already have ≥60 chars of snippet to avoid wasted fetches on re-scrapes.
- **Word-boundary keyword matching** — plain `phrase in text` causes false positives (e.g., "STATIN" inside "stating", "BIL" inside "billion"). Use `\b` regex boundaries.
- **Long-ticker keywords only (5+ chars)** — ticker-as-keyword for NCBFG/JMMBGL/WISYNCO etc., but NOT for CAR/GK/SJ/BIL/MGL (short tickers create substring noise even with word boundaries — e.g. "SJ" matches "SJC", "GK" matches "GKK"). Trade-off accepted: short-ticker companies need their full name in headlines/bodies to be auto-caught.
- **Soft-delete for tag removal (`removed_at` column)** — when a user removes an auto/thematic tag via the UI, we set `removed_at` instead of deleting. Re-scrapes skip recreating any (article, stock) pair that has a soft-deleted row. User's "no" is permanent.
- **Add manual = restore-or-insert** — adding a manual tag for an (article, stock) pair where a soft-deleted row exists restores that row and flips it to `source='manual'`, instead of inserting a duplicate. Same `link_id` survives across the remove → add cycle.

**Long-term vision (founder intent):**
Eventually sell JSEdge as a premium product to other JSE investors — so they can make informed decade-investing decisions, not just me. Trust and data quality must come before deploy.