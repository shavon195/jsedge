# JSEdge — Next Session

## 🎯 Quick-resume

```bash
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
# then open http://localhost:8000
```

## ✅ Done so far (23 commits)

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

**News scraper foundation (Session 1 of 3 — commit 3ed7281)**
- Jamaica Gleaner business section scraper
- Keyword dictionary: 23 JSE stocks, ~50 phrase variants (`app/news_keywords.py`)
- Themes system: 6 macro themes (tourism, oil_energy, usd_jmd, interest_rates, insurance_sector, distribution_retail), ~80 keywords, 12 affected stocks (`app/news_themes.py`)
- Two-table DB schema: `news_articles` + `news_stock_links`
- Save pipeline with smart upsert (preserves `ai_summary`) and surgical link cleanup (preserves manual tags)
- Real-data test: 7 of 10 articles correctly tagged (4 direct, 3 thematic)

---

## ⚠️ Mid-session bug to verify FIRST

**File:** `app/news_scraper.py`, function `scrape_gleaner_business()`.

We may have just fixed a bug where `matched_themes` wasn't being assigned to the article dict before returning. The fix line is:

```python
art["matched_themes"] = rel["matched_themes"]
```

To verify the fix works:
1. Wipe news tables: `python scripts/wipe_news.py` (file may not exist yet — create it if needed)
2. Re-run pipeline: `python scripts/scrape_news.py`
3. Expected: 7 articles, ~5 auto links, ~6 thematic links
4. If still showing only 5 articles or 0 thematic links → the fix didn't take. Need to re-verify the function.

---

## 🚧 TODO — in priority order

### 1. Finish News scraper (Sessions 2 & 3, ~5-7 hours)
- **Session 2:** Add Observer + JSE filings sources. Build the override UI (manual tag/untag).
- **Session 3:** Gemini API integration for AI summaries. Build the `/news` tab display.

### 2. ⚠️ AUTH BEFORE DEPLOY (~75 min) — locked-in requirement
Password-protect `/fundamentals` admin pages.
- Install `itsdangerous` + `python-dotenv`
- `.env` with `ADMIN_PASSWORD` and `SESSION_SECRET`
- Session middleware + signed cookies
- `/admin/login` and `/admin/logout` routes + login template
- `require_admin` decorator on all `/fundamentals/*` routes
- Login indicator in top nav
- **Must be done BEFORE deploying to Render** — otherwise anyone on the internet can edit data

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

# News scraper — full pipeline (Gleaner only for now)
python scripts/scrape_news.py

# News scraper debug — see what's being filtered and why
python scripts/debug_news_scraper.py
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

**News scraper design (Session 1):**
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

**Long-term vision (founder intent):**
Eventually sell JSEdge as a premium product to other JSE investors — so they can make informed decade-investing decisions, not just me. Trust and data quality must come before deploy.