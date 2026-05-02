"""
JSEdge — Database setup and connection.

This module handles:
- Where the SQLite database file lives
- How to open a connection to it
- The full schema definition (all tables)
"""

import sqlite3
from pathlib import Path

# --------------------------------------------------------------------------
# Database location
# --------------------------------------------------------------------------
# Path(__file__) gives the path to this file (app/database.py).
# .parent goes up to app/, then .parent again to the project root,
# then we append data/jsedge.db so the DB lives in data/.
DB_PATH = Path(__file__).parent.parent / "data" / "jsedge.db"


# --------------------------------------------------------------------------
# Connection helper
# --------------------------------------------------------------------------
def get_connection() -> sqlite3.Connection:
    """
    Open a connection to the JSEdge database.

    Always close it when done, or use it inside a 'with' block which
    closes automatically.
    """
    conn = sqlite3.connect(DB_PATH)
    # Make rows behave like dictionaries: row["symbol"] instead of row[0].
    conn.row_factory = sqlite3.Row
    # SQLite has foreign keys turned OFF by default — turn them on.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# --------------------------------------------------------------------------
# Schema definition — the SQL that creates every table
# --------------------------------------------------------------------------
SCHEMA_SQL = """
-- 1. Master list of every JSE-listed stock.
CREATE TABLE IF NOT EXISTS stocks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    market      TEXT    NOT NULL CHECK (market IN ('Main Market', 'Junior Market', 'USD Market')),
    sector      TEXT,
    currency    TEXT    NOT NULL DEFAULT 'JMD',
    is_listed   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- 2. Daily closing price + volume for every stock. Grows forever.
CREATE TABLE IF NOT EXISTS prices_daily (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id      INTEGER NOT NULL,
    date          TEXT    NOT NULL,
    close_price   REAL    NOT NULL,
    open_price    REAL,
    high_price    REAL,
    low_price     REAL,
    volume        INTEGER,
    market_cap    REAL,
    todays_range   TEXT,
    week52_range   TEXT,
    div_prev_year  REAL,
    div_curr_year  REAL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (stock_id) REFERENCES stocks(id) ON DELETE CASCADE,
    UNIQUE (stock_id, date)
);

CREATE INDEX IF NOT EXISTS idx_prices_stock_date ON prices_daily(stock_id, date);
CREATE INDEX IF NOT EXISTS idx_prices_date       ON prices_daily(date);

-- 3. Fundamentals — financial metrics per stock per reporting period.
CREATE TABLE IF NOT EXISTS fundamentals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id            INTEGER NOT NULL,
    report_date         TEXT    NOT NULL,
    period_type         TEXT    NOT NULL CHECK (period_type IN ('quarterly', 'annual')),
    eps                 REAL,
    pe_ratio            REAL,
    pb_ratio            REAL,
    dividend_yield      REAL,
    total_debt          REAL,
    total_equity        REAL,
    net_income          REAL,
    revenue             REAL,
    shares_outstanding  REAL,
    source              TEXT    NOT NULL CHECK (source IN ('scraped', 'manual')),
    notes               TEXT,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (stock_id) REFERENCES stocks(id) ON DELETE CASCADE,
    UNIQUE (stock_id, report_date, period_type)
);

CREATE INDEX IF NOT EXISTS idx_fundamentals_stock ON fundamentals(stock_id);

-- 4. Calculated ranking score per stock per day.
CREATE TABLE IF NOT EXISTS scores (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id          INTEGER NOT NULL,
    date              TEXT    NOT NULL,
    composite_score   REAL    NOT NULL,
    pe_score          REAL,
    growth_score      REAL,
    roe_score         REAL,
    debt_score        REAL,
    dividend_score    REAL,
    pb_score          REAL,
    position_score    REAL,
    volume_score      REAL,
    range_score       REAL,
    data_completeness REAL,
    fair_value        REAL,
    margin_of_safety  REAL,
    notes             TEXT,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (stock_id) REFERENCES stocks(id) ON DELETE CASCADE,
    UNIQUE (stock_id, date)
);

CREATE INDEX IF NOT EXISTS idx_scores_stock_date ON scores(stock_id, date);
CREATE INDEX IF NOT EXISTS idx_scores_date       ON scores(date);

-- 5. Watchlist — stocks the user is tracking with target buy prices.
CREATE TABLE IF NOT EXISTS watchlist (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id      INTEGER NOT NULL UNIQUE,
    limit_price   REAL,
    target_shares INTEGER,
    notes         TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    added_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (stock_id) REFERENCES stocks(id) ON DELETE CASCADE
);

-- 6. Alerts log — history of alerts already sent (so we don't spam).
CREATE TABLE IF NOT EXISTS alerts_log (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id           INTEGER NOT NULL,
    alert_type         TEXT    NOT NULL CHECK (alert_type IN
                                ('LIMIT_PRICE_HIT', 'SCORE_THRESHOLD', 'VOLUME_SPIKE', 'DAILY_BRIEF')),
    message_summary    TEXT    NOT NULL,
    delivered_via      TEXT    CHECK (delivered_via IN ('whatsapp', 'email', 'both', 'failed')),
    sent_at            TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (stock_id) REFERENCES stocks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_alerts_stock ON alerts_log(stock_id, sent_at);

-- 7. Purchases — log of stocks you actually bought (manually entered after
-- you execute a buy through NCB Capital Markets).
CREATE TABLE IF NOT EXISTS purchases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id        INTEGER NOT NULL,
    purchase_date   TEXT    NOT NULL,
    shares          INTEGER NOT NULL,
    price_per_share REAL    NOT NULL,
    fees            REAL    DEFAULT 0,
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (stock_id) REFERENCES stocks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_purchases_stock ON purchases(stock_id, purchase_date);

-- 8. Account balance snapshots — track cash + portfolio value over time.
-- One row per manual entry (e.g., when you top up monthly).
CREATE TABLE IF NOT EXISTS account_balance (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date     TEXT    NOT NULL,
    cash_balance      REAL    NOT NULL,
    deposit_amount    REAL    DEFAULT 0,
    portfolio_value   REAL,
    notes             TEXT,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_balance_date ON account_balance(snapshot_date);

-- 9. User settings — flexible key-value store for app preferences.
-- Edit these via the settings page (button toggles update rows here).
CREATE TABLE IF NOT EXISTS user_settings (
    key         TEXT    PRIMARY KEY,
    value       TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Seed default settings. INSERT OR IGNORE means: only insert if the key
-- doesn't already exist. Lets us re-run setup safely without overwriting
-- the user's choices.
INSERT OR IGNORE INTO user_settings (key, value) VALUES
    ('alert_mode',           'daily_brief'),     -- 'aggressive' or 'daily_brief'
    ('daily_brief_time',     '08:00'),           -- 24h time, local
    ('alerts_whatsapp',      'true'),
    ('alerts_email',         'true'),
    ('whatsapp_number',      ''),                -- filled later via settings page
    ('email_address',        ''),
    ('margin_of_safety_pct', '20'),              -- default 20% margin
    ('min_score_threshold',  '70'),              -- alert if score crosses this
    ('summary_provider',     'gemini'),          -- 'gemini', 'claude', or 'none'
    ('gemini_api_key',       ''),                -- filled later via settings page
    ('claude_api_key',       '');                -- filled later via settings page
"""


def initialize_database() -> None:
    """
    Create all tables defined in SCHEMA_SQL.

    Safe to run multiple times — every CREATE TABLE uses IF NOT EXISTS,
    and seed inserts use INSERT OR IGNORE, so existing data is preserved.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        print(f"✅ Database initialized at: {DB_PATH}")
    finally:
        conn.close()