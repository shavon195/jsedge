# JSEdge — Next Session

## 🎯 Quick-resume

```bash
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
# then open http://localhost:8000
```

## ✅ Done so far (20 commits)

**Foundation**
- FastAPI server with 3 tabs (JSE / News / Trading)
- SQLite schema with 9 tables (stocks, prices_daily, fundamentals, scores, watchlist, alerts_log, purchases, account_balance, user_settings)
- 101 stocks loaded (53 Main Market + 48 Junior)

**Scraper**
- JSE static-HTML scraper with retry logic, empty-page detection, low-count warnings
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
- Real data entered: **CAR (Carreras Limited) FY2024**

**Dashboard**
- Horizon dropdown on JSE tab — switches between 6mo / 1yr / 2yr / 5yr / 10+yr
- Context-sensitive disclosure banners per horizon
- Default horizon: **10+ years** (decade portfolio is JSEdge's identity)

---

## 🚧 TODO — in priority order

### 1. ⚠️ AUTH BEFORE DEPLOY (~75 min) — locked-in requirement
Password-protect `/fundamentals` admin pages.
- Install `itsdangerous` + `python-dotenv`
- `.env` with `ADMIN_PASSWORD` and `SESSION_SECRET`
- Session middleware + signed cookies
- `/admin/login` and `/admin/logout` routes + login template
- `require_admin` decorator on all `/fundamentals/*` routes
- Login indicator in top nav
- **Must be done BEFORE deploying to Render** — otherwise anyone on the internet can edit data

### 2. Enter more fundamentals data (~6-13 hours, paced over weeks)
Goal: 80 companies of fundamentals data so the 5yr/10yr rankings come alive.

Recommended early picks (non-bank, simple financials):
- WISYNCO (Wisynco)
- GK (GraceKennedy)
- LASD (Lasco Distributors)
- DCOVE (Dolphin Cove)
- JBG (Jamaica Broilers)

Defer until non-bank pattern is solid:
- NCBFG, JMMBGL, BIL (banks have weird financials — deposits, lease quirks)

### 3. Watchlist + price alerts (~4-6 hours)
Schema already exists. Build:
- "Add to watchlist" button on stock pages
- Watchlist tab on JSE page
- Set limit prices per stock
- Trigger alerts when price hits the limit

### 4. WhatsApp + email alerts (~6-8 hours)
- Twilio (WhatsApp) integration
- Resend (email) integration
- User toggle: which alerts go where
- Daily summary at market close

### 5. Deploy to Render or Railway (~3-4 hours)
- **Auth (#1) must be done first**
- GitHub Actions for daily scrape
- Persistent SQLite or migrate to PostgreSQL
- Custom domain optional

### 6. News tab — Phase 2 (~10-15 hours)
- Scrape Gleaner / Observer / JSE filings
- AI summaries (Gemini default, Claude switchable)
- News card per stock

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

# Run scraper (offline against saved sample)
python scripts/run_scraper.py --offline --date 2026-04-28

# Run scraper (live)
python scripts/run_scraper.py --date YYYY-MM-DD
```

---

## 📐 Design decisions (for future-me)

- **Numbers stored raw** (J$19,551,584,000 not abbreviated) — avoids unit confusion
- **Manual fundamentals entry, NOT AI extraction** — too high hallucination risk for financial numbers
- **Two-tier ranking** (main + incomplete) — same pattern across technical and fundamentals
- **Default horizon = 10_years** — JSEdge's identity is decade investing
- **Strong horizon weight differences** — short = technical, long = fundamentals (no overlap)
- **Strict historical depth** — long horizons require multi-year fundamentals
- **Option B for scoring storage** — pre-compute all 5 horizons (chosen over on-the-fly to learn the cost firsthand; YAGNI lesson)
- **Operating income proxy = profit before tax** — when no clean operating income line exists in JSE filings