# JSEdge — Next Session

## 🎯 Quick-resume

```bash
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
# then open http://localhost:8000
```

Daily automation runs via Windows Task Scheduler — see "Automation" section below.

---

## ✅ Done so far (~40 commits)

### Foundation
- FastAPI server with 5 tabs (JSE / News / Trading / Watchlist / Fundamentals)
- SQLite schema with 11 tables
- 101 stocks loaded (53 Main + 48 Junior)

### JSE Scraper
- Static-HTML scraper with retry, empty-page detection, low-count warnings
- Idempotent saves via ON CONFLICT
- Now scheduled daily at 5:00 PM via Task Scheduler

### Ranking engine — horizon-aware
- 8 sub-scores: 4 technical + 4 fundamentals
- 5 horizons: 6mo / 1yr / 2yr / 5yr / 10+yr — each with its own weight matrix
- Strict historical depth gating, 75% completeness threshold
- Default horizon: **10+ years**

### News system
- Gleaner + Observer scrapers (Observer enriches thin snippets)
- Keyword dictionary (23 stocks) + themes (6 macro categories)
- `/news` page with auto/thematic/manual tag types
- Soft-delete tags, manual override UI
- AI summaries via Gemini (per-article button)
- Refresh news button (admin-only)
- Real-data baseline: ~10 articles/day, ~9 auto + ~5 thematic links

### Fundamentals data entry
- Per-stock list page with progress bar + smart sort
- 13-field add/edit/delete with flash banners
- Save & Add Another, Prev/Next nav
- Real data entered so far: **CAR, WISYNCO** (2 of ~100)

### Admin authentication
- `.env`-based password + signed session cookies (`itsdangerous`)
- `/admin/login` and `/admin/logout` routes
- `require_admin` dependency on 10 write routes
- Public read-only view (rankings + news + AI summaries)
- Admin-only UI: refresh button, summarize button, tag controls, fundamentals tab, watchlist tab

### Watchlist (admin-only)
- ★ button on every JSE ranking row (Main + Incomplete tables)
- `/watchlist` page with current price, editable target, gap %, hit/near/far states
- Filter pills: Active / Hit targets / Inactive
- Expandable rows showing price context: 1-year range, 3-month low, quick-target buttons (-10/-20/-30%)
- Soft-delete pattern (re-adding restores)

### Alerts system (LIVE — daily automation)
- **Email channel:** Resend API integration, sends from `onboarding@resend.dev`
- **WhatsApp channel:** Twilio Sandbox, +14155238886 sandbox number, "join public-production" code activated
- **Dispatcher:** target-hit detection with 7-day cooldown (prevents alert spam)
- **Keep-alive:** rotating Bible verses, fires if 48+ hours of WhatsApp silence
- **Daily runner:** `scripts/run_daily_alerts.py` orchestrates the full pipeline
- `alerts_log` migration: `stock_id` now nullable to support non-stock alerts
- All credentials saved securely in `user_settings` table (masked in `check_settings.py`)

### Automation (Windows Task Scheduler)
| Task | Schedule | Script |
|------|----------|--------|
| JSEdge Daily Price Scrape | 5:00 PM daily | `scripts/run_scraper.py` |
| JSEdge Daily Alerts | 9:20 AM daily | `scripts/run_daily_alerts.py` |

Both tasks: AC-power constraints removed, "run after missed schedule" enabled.

---

## 🚧 TODO — in priority order

### 1. Historical price backfill (~3-5 hours)
**Problem:** `prices_daily` only has 2 days of data so far. Watchlist's 1-year range shows `$X.XX — $X.XX` (same number) because there's no history yet.

**Plan:**
- Investigate where JSE historical CSV / API data lives
- Bulk-import 1 year of close prices for top 20 stocks (CAR, WISYNCO, NCBFG, JMMBGL, GK, LASD, DCOVE, JBG, BIL, etc.)
- Add data-retention cap: delete `prices_daily` rows older than 730 days during nightly scrape (prevents DB bloat)

### 2. Curate Bible verse list for keep-alive (~30 min, paced)
Currently `app/alerts/dispatcher.py` has 7 placeholder verses. Replace with Shavon's curated list of 30-50 verses. Edit `KEEP_ALIVE_VERSES` constant.

### 3. Polish features (optional, ~3-4 hours total)
- **Settings UI** (~1-2h): web form to manage email/phone/API keys without running scripts
- **Alert history page** (~30 min): view past `alerts_log` rows in the web UI
- **Summary emails** (~1-2h): scheduled daily/weekly/monthly digest emails

### 4. More fundamentals data entry (paced, weeks)
Goal: 10-20 companies of fundamentals so 5yr/10yr rankings come alive.
Done: CAR, WISYNCO.
Next picks (non-bank, simple financials): GK, LASD, DCOVE, JBG.
Defer banks until non-bank pattern is solid: NCBFG, JMMBGL, BIL.

### 5. Trading tab (Phase 3) — biggest remaining feature (~15-25 hours)
- Technical indicators: RSI, MACD, moving averages, Bollinger Bands
- Signal engine: buy/sell signals from technicals
- TradingView integration (embedded charts + webhook receiver)
- Backtesting against historical scores
- Paper-trading first to validate before risking real money

### 6. Deploy to Render or Railway (~3-4 hours) — LAST FEATURE
- Move to cloud server (always-on, replaces local laptop scheduling)
- GitHub Actions or platform cron for daily scrape + alerts
- Persistent SQLite or migrate to PostgreSQL
- Disable Windows Task Scheduler entries after deploy succeeds
- Custom domain optional

### 7. Future — JSE filings scraper (~20+ hours)
Auto-extract fundamentals from JSE filings PDFs instead of manual entry.
Defer until non-bank pattern is solid (5+ companies entered manually).

### 8. Tech debt
- `app/database.py` SCHEMA_SQL is missing `news_articles` and `news_stock_links` definitions — they were created out-of-band. Reconcile next time we rebuild the DB.
- `news_stock_links.removed_at` was added via migration; should be in SCHEMA_SQL too.
- `alerts_log` was migrated to nullable `stock_id`; SCHEMA_SQL was updated to match (already done today).

---

## 📋 Verification commands

```bash
# Inspect database
python scripts/check_db.py

# Inspect user_settings (sensitive values masked)
python scripts/check_settings.py

# Re-run scoring across all 5 horizons
python scripts/compute_all_horizons.py

# Run JSE price scraper (live — uses today's date)
python scripts/run_scraper.py

# Run JSE price scraper for a specific date
python scripts/run_scraper.py --date 2026-05-15

# Run the full alert pipeline (target check + keep-alive)
python scripts/run_daily_alerts.py

# News scraper — full pipeline (Gleaner + Observer)
python scripts/scrape_news.py

# Test email channel
python -c "from app.alerts.email import send_test_email; print(send_test_email())"

# Test WhatsApp channel
python -c "from app.alerts.whatsapp import send_test_whatsapp; print(send_test_whatsapp())"

# Force a keep-alive WhatsApp (bypasses 48hr cooldown)
python -c "from app.alerts.dispatcher import send_keep_alive; print(send_keep_alive(force=True))"

# Save/update a credential (gemini_api_key, resend_api_key, twilio_account_sid,
# twilio_auth_token, email_address, whatsapp_number, claude_api_key)
python scripts/set_api_key.py <key_name>

# Look up a stock by name fragment
python scripts/find_stock.py first
```

---

## 🔐 Saved credentials (in `user_settings` table)

| Key | Status |
|-----|--------|
| `gemini_api_key` | ✅ working (Gemini AI summaries) |
| `resend_api_key` | ✅ working (email alerts) |
| `twilio_account_sid` | ✅ working |
| `twilio_auth_token` | ✅ working |
| `whatsapp_number` | ✅ working (Twilio Sandbox activated) |
| `email_address` | ✅ working |
| `claude_api_key` | empty (not used) |

---

## 🧠 Key product decisions logged

- **Single-user (admin-only) model.** Multi-user explicitly rejected after thorough discussion. If JSEdge ever opens up publicly, a separate v2 migration would add real user accounts. Current schema has UNIQUE(stock_id) on watchlist which enforces single-user.
- **Hybrid alerts:** WhatsApp for time-critical (target hits), email durable backup. Keep-alive solves Twilio sandbox 72-hour window.
- **No "smart" auto-target prices.** Watchlist shows price context (year range, quick targets) but user always picks the target. Reasoning: AI-generated targets would create false confidence on real money decisions.
- **Fundamentals data entry deferred to LAST** before deploy — chat sessions can fragment during long data entry, but framework code is in git regardless.
- **Refresh + summarize buttons admin-only.** Public visitors get fresh data via daily cron; manual refresh stays gated to prevent cost / DDoS surface area.