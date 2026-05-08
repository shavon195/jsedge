"""
JSEdge — Ranking engine.

Computes a 0-100 composite "buy attractiveness" score per stock based on
technical signals available in our daily scrape:

    1. Position score   (30%) — how close to 52-week low (lower = better)
    2. Volume score     (25%) — liquidity vs the rest of the market
    3. Dividend score   (25%) — yield as % of price
    4. Range score      (20%) — intraday stability (tight range = better)

Stocks with full data go in the main ranking. Stocks missing 25%+ of
signals go in a separate "incomplete data" ranking, also sorted by score.
"""

import logging
import math
from datetime import date
from typing import Optional

from app.database import get_connection

# Set up logging consistent with the rest of the app.
log = logging.getLogger(__name__)



# Horizon-aware weights — different metrics matter for different time frames
# ---------------------------------------------------------------------------
# Each horizon is a dict of {signal_name: weight}. Weights within a horizon
# must sum to 1.0. Missing signals (not in a horizon's dict) contribute 0.
#
# The 4 technical signals come from prices_daily (scraped daily):
#     position, volume, dividend, range
# The 4 fundamentals signals come from the fundamentals table (manual entry):
#     roe, fcf_margin, debt, profit_margin
#
# Short horizons (6mo, 1yr) lean technical — what's moving NOW.
# Long horizons (5yr, 10yr+) lean fundamentals — what's a quality business.
HORIZON_WEIGHTS = {
    "6_months": {
        "position":      0.30,
        "volume":        0.25,
        "dividend":      0.25,
        "range":         0.20,
    },
    "1_year": {
        "position":      0.25,
        "volume":        0.20,
        "dividend":      0.30,
        "range":         0.10,
        "profit_margin": 0.15,
    },
    "2_years": {
        "position":      0.10,
        "volume":        0.10,
        "dividend":      0.20,
        "roe":           0.20,
        "profit_margin": 0.20,
        "fcf_margin":    0.15,
        "debt":          0.05,
    },
    "5_years": {
        "dividend":      0.15,
        "roe":           0.25,
        "profit_margin": 0.20,
        "fcf_margin":    0.25,
        "debt":          0.15,
    },
    "10_years": {
        "dividend":      0.10,
        "roe":           0.25,
        "profit_margin": 0.15,
        "fcf_margin":    0.30,
        "debt":          0.20,
    },
}

# Default horizon used when none is specified — the new "main" view of JSEdge.
DEFAULT_HORIZON = "10_years"

# Backward-compat: keep the old WEIGHTS name pointing at the 6-month horizon
# so any existing code that imports WEIGHTS keeps working.
WEIGHTS = HORIZON_WEIGHTS["6_months"]

# Stocks need at least this fraction of signals with valid data to qualify
# for the main ranking. Below this, they go into the "incomplete" list.
MAIN_RANKING_THRESHOLD = 0.75

# Historical depth requirements (per Q5: A — strict)
# Stocks failing these go to "incomplete data" automatically.
MIN_FUNDAMENTALS_ROWS = {
    "6_months": 0,   # no requirement — technical only
    "1_year":   0,
    "2_years":  1,   # at least 1 fundamentals row
    "5_years":  3,   # at least 3 years of data
    "10_years": 5,   # at least 5 years of data
}

# ---------------------------------------------------------------------------
# Helper — parse range strings like "2.85 - 3.35"
# ---------------------------------------------------------------------------
def parse_range_string(text: Optional[str]) -> Optional[tuple[float, float]]:
    """
    Convert a 'low - high' range string into a (low, high) tuple of floats.

    JSE range fields look like:
        "2.85 - 3.35"
        "164.20 - 383.52"
        "0.00 - 0.00"   (no trades)

    Args:
        text: the range string, or None.

    Returns:
        Tuple (low, high) or None if the string is missing/malformed/zero.
    """
    if not text or not isinstance(text, str):
        return None

    parts = text.split("-")
    if len(parts) != 2:
        return None

    try:
        low  = float(parts[0].strip().replace(",", ""))
        high = float(parts[1].strip().replace(",", ""))
    except ValueError:
        return None

    # Treat 0.00 - 0.00 as missing data (some stocks didn't trade).
    if low == 0 and high == 0:
        return None

    # Sanity: low should be <= high. If reversed, swap them silently.
    if low > high:
        low, high = high, low

    return low, high


# ---------------------------------------------------------------------------
# Sub-score 1: 52-week position
# ---------------------------------------------------------------------------
def compute_position_score(
    current_price: Optional[float],
    week52_range:  Optional[str],
) -> Optional[float]:
    """
    Score 0-100 based on where the current price sits in its 52-week range.
    
    Lower in the range = higher score (we like buying near lows).
        - At 52w low:  score = 100
        - In middle:   score =  50
        - At 52w high: score =   0
    
    Args:
        current_price: today's closing price.
        week52_range:  string like "2.55 - 4.78".
    
    Returns:
        Score 0-100, or None if data is missing/invalid.
    """
    if current_price is None or current_price <= 0:
        return None

    parsed = parse_range_string(week52_range)
    if parsed is None:
        return None

    low, high = parsed

    # If high == low, range has no width — treat as no signal.
    if high <= low:
        return None

    # Position 0.0 = at low, 1.0 = at high.
    position = (current_price - low) / (high - low)

    # Clamp to [0, 1] in case price is briefly outside the 52w range
    # (happens occasionally — JSE data can lag, or a new high gets set).
    position = max(0.0, min(1.0, position))

    # Invert: low position -> high score.
    return round(100 * (1.0 - position), 2)


# ---------------------------------------------------------------------------
# Sub-score 2: Volume / liquidity
# ---------------------------------------------------------------------------
def compute_volume_score(
    volume:        Optional[int],
    market_volumes: list[int],
) -> Optional[float]:
    """
    Score 0-100 based on how this stock's volume compares to the market.

    Uses a log-scale comparison against the median volume:
        - At median:           score =  50
        - 10x above median:    score = ~85
        - 10x below median:    score = ~15
        - 100x above median:   score = capped at 100
        - Zero volume:         score =   0 (suspicious)

    Args:
        volume:         this stock's daily volume.
        market_volumes: list of all stocks' volumes for the same day,
                        used to establish the median.

    Returns:
        Score 0-100, or None if volume data is missing.
    """
    if volume is None:
        return None

    # Zero volume = nobody traded today. Worst case for liquidity.
    if volume == 0:
        return 0.0

    # Filter to positive volumes only — zeros would skew the median.
    positives = [v for v in market_volumes if v and v > 0]
    if len(positives) < 5:
        # Not enough comparison data to score against.
        return None

    # Median = middle value when sorted.
    sorted_vols = sorted(positives)
    median = sorted_vols[len(sorted_vols) // 2]

    if median <= 0:
        return None

    # log10 ratio: 0.0 = at median, +1.0 = 10x above, -1.0 = 10x below.
    ratio = math.log10(volume / median)

    # Map to 0-100. Each log10 step = 35 score points.
    # Median (ratio=0) -> 50. Cap at 0 and 100.
    score = 50 + ratio * 35
    score = max(0.0, min(100.0, score))

    return round(score, 2)

# ---------------------------------------------------------------------------
# Sub-score 3: Dividend yield
# ---------------------------------------------------------------------------
def compute_dividend_score(
    current_price:    Optional[float],
    div_prev_year:    Optional[float],
    div_curr_year:    Optional[float],
) -> Optional[float]:
    """
    Score 0-100 based on dividend yield.

    Yield = annual_dividend / current_price.

    We use the higher of (prev_year, curr_year) dividend to be optimistic
    about future income — recent dividends are the best estimate of future ones.

    Yield-to-score map (rough JSE benchmark):
        0.0% -> score   0
        2.0% -> score  40
        5.0% -> score  75
        8.0% -> score 100  (capped)

    Args:
        current_price: today's closing price.
        div_prev_year: total dividends paid previous fiscal year.
        div_curr_year: total dividends paid current fiscal year so far.

    Returns:
        Score 0-100, or None if data is missing.
    """
    if current_price is None or current_price <= 0:
        return None

    # Use the larger of the two available dividend figures.
    candidates = [d for d in (div_prev_year, div_curr_year) if d is not None]
    if not candidates:
        return None

    annual_dividend = max(candidates)

    # No dividend at all → score 0 (not None — this IS a signal, not missing data).
    if annual_dividend <= 0:
        return 0.0

    yield_pct = (annual_dividend / current_price) * 100

    # Linear map from yield to score, capped at 100.
    # Each 1% yield = 12.5 score points.
    score = yield_pct * 12.5
    score = max(0.0, min(100.0, score))

    return round(score, 2)

# ---------------------------------------------------------------------------
# Sub-score 4: Intraday range stability
# ---------------------------------------------------------------------------
def compute_range_score(
    current_price: Optional[float],
    todays_range:  Optional[str],
) -> Optional[float]:
    """
    Score 0-100 based on intraday price stability.

    Tight range = predictable = higher score.

    Range%-to-score map:
        0%   range -> score 100  (perfectly stable, no movement)
        2%   range -> score  80  (typical blue-chip)
        5%   range -> score  50  (moderate volatility)
        10%+ range -> score   0  (high volatility, unpredictable)

    Args:
        current_price: today's closing price.
        todays_range:  string like "2.85 - 3.35".

    Returns:
        Score 0-100, or None if data is missing/invalid.
    """
    if current_price is None or current_price <= 0:
        return None

    parsed = parse_range_string(todays_range)
    if parsed is None:
        return None

    low, high = parsed
    range_width = high - low

    # Express range as a percentage of price.
    range_pct = (range_width / current_price) * 100

    # Linear map: 0% -> 100, 10% -> 0. Each 1% range loses 10 score points.
    score = 100 - (range_pct * 10)
    score = max(0.0, min(100.0, score))

    return round(score, 2)

# ---------------------------------------------------------------------------
# Sub-score 5: ROE (Return on Equity) — quality of profit generation
# ---------------------------------------------------------------------------
def compute_roe_score(
    net_income:   Optional[float],
    total_equity: Optional[float],
) -> Optional[float]:
    """
    Score 0-100 based on Return on Equity (ROE = net_income / total_equity).

    ROE measures how efficiently a company generates profit from shareholders'
    money. Buffett-style threshold: 15%+ ROE sustained over years = quality.

    ROE-to-score map:
        - ROE  ≥ 20%   -> score = 100   (excellent compounder)
        - ROE  = 15%   -> score = ~75   (good quality)
        - ROE  = 10%   -> score = ~50   (acceptable)
        - ROE  = 5%    -> score = ~25   (weak)
        - ROE  ≤ 0%    -> score =   0   (losing money)
    """
    if net_income is None or total_equity is None or total_equity <= 0:
        return None

    roe_pct = (net_income / total_equity) * 100

    # Linear scale: 0% ROE -> 0, 20% ROE -> 100. Each 1% = 5 points.
    score = roe_pct * 5
    return round(max(0.0, min(100.0, score)), 2)


# ---------------------------------------------------------------------------
# Sub-score 6: FCF Margin — cash quality of profits
# ---------------------------------------------------------------------------
def compute_fcf_margin_score(
    free_cash_flow: Optional[float],
    revenue:        Optional[float],
) -> Optional[float]:
    """
    Score 0-100 based on Free Cash Flow margin (FCF / Revenue).

    FCF margin shows how much actual cash a company generates per dollar of
    revenue. Higher = healthier business. Buffett's favorite metric.

    FCF margin-to-score map:
        - FCF margin ≥ 25%  -> score = 100   (exceptional)
        - FCF margin = 15%  -> score = ~60   (great)
        - FCF margin = 8%   -> score = ~32   (decent)
        - FCF margin ≤ 0%   -> score =   0   (burning cash)
    """
    if free_cash_flow is None or revenue is None or revenue <= 0:
        return None

    fcf_margin_pct = (free_cash_flow / revenue) * 100

    # 0% margin -> 0, 25% margin -> 100. Each 1% = 4 points.
    score = fcf_margin_pct * 4
    return round(max(0.0, min(100.0, score)), 2)


# ---------------------------------------------------------------------------
# Sub-score 7: Debt-to-Equity — financial safety
# ---------------------------------------------------------------------------
def compute_debt_score(
    total_debt:   Optional[float],
    total_equity: Optional[float],
) -> Optional[float]:
    """
    Score 0-100 based on Debt-to-Equity ratio (total_debt / total_equity).

    Lower debt = safer through downturns. Critical for decade holds.

    D/E-to-score map:
        - D/E  ≤ 0.3   -> score = 100   (very safe)
        - D/E  = 0.5   -> score = ~80
        - D/E  = 1.0   -> score = ~50   (moderate)
        - D/E  = 2.0   -> score = ~10   (risky)
        - D/E  ≥ 3.0   -> score =   0   (dangerous)

    Note: zero debt with positive equity = score 100 (safest possible).
    """
    if total_equity is None or total_equity <= 0:
        return None

    if total_debt is None:
        return None

    if total_debt < 0:
        total_debt = 0  # treat negative debt as zero (data quirk)

    de_ratio = total_debt / total_equity

    # Linear inverse: D/E 0 -> 100, D/E 3 -> 0. Each 0.1 D/E = ~3.33 points loss.
    score = 100 - (de_ratio * 33.33)
    return round(max(0.0, min(100.0, score)), 2)


# ---------------------------------------------------------------------------
# Sub-score 8: Net Profit Margin — pricing power
# ---------------------------------------------------------------------------
def compute_profit_margin_score(
    net_income: Optional[float],
    revenue:    Optional[float],
) -> Optional[float]:
    """
    Score 0-100 based on Net Profit Margin (net_income / revenue).

    High margins = pricing power = moat. The hallmark of quality businesses.

    Margin-to-score map:
        - Margin ≥ 20%  -> score = 100   (premium business)
        - Margin = 15%  -> score = ~75
        - Margin = 10%  -> score = ~50
        - Margin = 5%   -> score = ~25   (commodity-like)
        - Margin ≤ 0%   -> score =   0   (unprofitable)
    """
    if net_income is None or revenue is None or revenue <= 0:
        return None

    margin_pct = (net_income / revenue) * 100

    # Linear: 0% -> 0, 20% -> 100. Each 1% = 5 points.
    score = margin_pct * 5
    return round(max(0.0, min(100.0, score)), 2)

# ---------------------------------------------------------------------------
# Composite score — combines all 4 sub-scores
# ---------------------------------------------------------------------------
def compute_composite_score(
    sub_scores: dict[str, Optional[float]],
    horizon: str = DEFAULT_HORIZON,
) -> dict:
    """
    Combine sub-scores into a single weighted composite for a given horizon.

    Each horizon (6_months, 1_year, 2_years, 5_years, 10_years) has its own
    weight matrix in HORIZON_WEIGHTS. Signals not in the horizon's matrix
    are ignored (their weight is effectively 0).

    Sub-scores that are None are EXCLUDED from the weighted average — we
    don't penalize a stock for missing data here; that's tracked separately
    via data_completeness so the caller can decide which list it belongs in.

    Args:
        sub_scores: dict of {signal_name: score 0-100 | None}.
                    Can include any of: position, volume, dividend, range,
                    roe, fcf_margin, debt, profit_margin.
        horizon:    one of HORIZON_WEIGHTS keys. Defaults to DEFAULT_HORIZON.

    Returns:
        Dict with:
            composite_score:   0-100 weighted average of available signals
            data_completeness: 0.0-1.0 fraction of horizon weight we had data for
            missing_signals:   list of signal names that this horizon wants
                               but were None in input
            horizon:           the horizon used (for downstream display)
    """
    # Pick the right weight matrix for this horizon.
    weights = HORIZON_WEIGHTS.get(horizon, HORIZON_WEIGHTS[DEFAULT_HORIZON])
    total_weight_for_horizon = sum(weights.values())  # always 1.0, but defensive

    weighted_sum = 0.0
    used_weight  = 0.0
    missing      = []

    # Only iterate signals this HORIZON cares about.
    for signal, weight in weights.items():
        score = sub_scores.get(signal)

        if score is None:
            missing.append(signal)
        else:
            weighted_sum += score * weight
            used_weight  += weight

    # If nothing scored, the stock has no usable signal at all.
    if used_weight == 0:
        return {
            "composite_score":   None,
            "data_completeness": 0.0,
            "missing_signals":   missing,
            "horizon":           horizon,
        }

    # Normalize: divide by used_weight so missing signals don't drag the
    # score toward zero. A stock with 1 perfect signal still scores 100.
    composite = weighted_sum / used_weight

    # Completeness = fraction of horizon weight we had data for.
    completeness = used_weight / total_weight_for_horizon

    return {
        "composite_score":   round(composite, 2),
        "data_completeness": round(completeness, 2),
        "missing_signals":   missing,
        "horizon":           horizon,
    }


# ---------------------------------------------------------------------------
# Score every stock for a given date
# ---------------------------------------------------------------------------
def score_all_stocks(
    target_date: date,
    horizon: str = DEFAULT_HORIZON,
) -> list[dict]:
    """
    Compute composite scores for every stock that has price data on the
    given date, using the weight matrix for the given horizon.

    For short horizons (6mo, 1yr) this is mostly technical scoring.
    For long horizons (5yr, 10yr) it leans heavily on fundamentals.

    Args:
        target_date: the trading day to score.
        horizon:     one of HORIZON_WEIGHTS keys. Defaults to DEFAULT_HORIZON.

    Returns:
        List of dicts, sorted descending by composite_score. Each dict has:
            stock_id, symbol, name, market,
            composite_score, data_completeness, missing_signals (list),
            horizon, fundamentals_rows (count for historical-depth gating),
            and all 8 individual sub-scores (None if not computed).
    """
    if horizon not in HORIZON_WEIGHTS:
        log.warning("Unknown horizon '%s', falling back to default.", horizon)
        horizon = DEFAULT_HORIZON

    min_rows_required = MIN_FUNDAMENTALS_ROWS.get(horizon, 0)

    conn = get_connection()
    try:
        # First pass: gather all volumes for the date so we can compute
        # the median used by the volume score.
        volumes_today = [
            r["volume"] for r in conn.execute(
                "SELECT volume FROM prices_daily WHERE date = ? AND volume IS NOT NULL",
                (target_date.isoformat(),),
            ).fetchall()
        ]

        log.info(
            "Scoring stocks for %s, horizon=%s (min_rows=%d, comparing %d volumes).",
            target_date.isoformat(), horizon, min_rows_required, len(volumes_today),
        )

        # Second pass: pull every stock with its price/range data,
        # plus the count of fundamentals rows it has, plus its MOST RECENT
        # fundamentals row (for ROE / FCF margin / debt / profit margin).
        rows = conn.execute(
            """
            SELECT
                s.id        AS stock_id,
                s.symbol    AS symbol,
                s.name      AS name,
                s.market    AS market,
                p.close_price,
                p.volume,
                p.todays_range,
                p.week52_range,
                p.div_prev_year,
                p.div_curr_year,
                (
                    SELECT COUNT(*) FROM fundamentals f
                    WHERE f.stock_id = s.id
                ) AS fundamentals_rows,
                (
                    SELECT f.net_income FROM fundamentals f
                    WHERE f.stock_id = s.id
                    ORDER BY f.period_end_date DESC LIMIT 1
                ) AS f_net_income,
                (
                    SELECT f.total_equity FROM fundamentals f
                    WHERE f.stock_id = s.id
                    ORDER BY f.period_end_date DESC LIMIT 1
                ) AS f_total_equity,
                (
                    SELECT f.total_debt FROM fundamentals f
                    WHERE f.stock_id = s.id
                    ORDER BY f.period_end_date DESC LIMIT 1
                ) AS f_total_debt,
                (
                    SELECT f.revenue FROM fundamentals f
                    WHERE f.stock_id = s.id
                    ORDER BY f.period_end_date DESC LIMIT 1
                ) AS f_revenue,
                (
                    SELECT f.free_cash_flow FROM fundamentals f
                    WHERE f.stock_id = s.id
                    ORDER BY f.period_end_date DESC LIMIT 1
                ) AS f_fcf
            FROM stocks s
            JOIN prices_daily p ON p.stock_id = s.id
            WHERE p.date = ?
            ORDER BY s.symbol
            """,
            (target_date.isoformat(),),
        ).fetchall()

    finally:
        conn.close()

    results = []

    for r in rows:
        # --- Technical sub-scores (always computed) ---
        position_score = compute_position_score(r["close_price"], r["week52_range"])
        volume_score   = compute_volume_score(r["volume"], volumes_today)
        dividend_score = compute_dividend_score(
            r["close_price"], r["div_prev_year"], r["div_curr_year"]
        )
        range_score    = compute_range_score(r["close_price"], r["todays_range"])

        # --- Fundamentals sub-scores (only if we have a recent row) ---
        roe_score = compute_roe_score(r["f_net_income"], r["f_total_equity"])
        fcf_margin_score = compute_fcf_margin_score(r["f_fcf"], r["f_revenue"])
        debt_score = compute_debt_score(r["f_total_debt"], r["f_total_equity"])
        profit_margin_score = compute_profit_margin_score(r["f_net_income"], r["f_revenue"])

        sub_scores = {
            "position":      position_score,
            "volume":        volume_score,
            "dividend":      dividend_score,
            "range":         range_score,
            "roe":           roe_score,
            "fcf_margin":    fcf_margin_score,
            "debt":          debt_score,
            "profit_margin": profit_margin_score,
        }

        result = compute_composite_score(sub_scores, horizon=horizon)

        # --- Historical depth gating (Q5 strict mode) ---
        fundamentals_rows = r["fundamentals_rows"] or 0
        if fundamentals_rows < min_rows_required:
            # Force this stock into the "incomplete data" tier.
            # We do this by capping completeness below the main threshold.
            if result["data_completeness"] >= MAIN_RANKING_THRESHOLD:
                result["data_completeness"] = MAIN_RANKING_THRESHOLD - 0.01
                result["missing_signals"].append(
                    f"insufficient history ({fundamentals_rows}/{min_rows_required} rows)"
                )

        # Build a notes string for the incomplete-data list.
        notes = None
        if result["missing_signals"]:
            notes = "missing: " + ", ".join(result["missing_signals"])

        results.append({
            "stock_id":            r["stock_id"],
            "symbol":              r["symbol"],
            "name":                r["name"],
            "market":              r["market"],
            "horizon":             horizon,
            "composite_score":     result["composite_score"],
            "position_score":      position_score,
            "volume_score":        volume_score,
            "dividend_score":      dividend_score,
            "range_score":         range_score,
            "roe_score":           roe_score,
            "fcf_margin_score":    fcf_margin_score,
            "debt_score":          debt_score,
            "profit_margin_score": profit_margin_score,
            "data_completeness":   result["data_completeness"],
            "fundamentals_rows":   fundamentals_rows,
            "notes":               notes,
        })

    # Sort by composite score (None goes last, then descending).
    results.sort(
        key=lambda x: (x["composite_score"] is None, -(x["composite_score"] or 0))
    )

    log.info(
        "Scored %d stocks for %s, horizon=%s.",
        len(results), target_date.isoformat(), horizon,
    )
    return results

# ---------------------------------------------------------------------------
# Persist scores to the database
# ---------------------------------------------------------------------------
def save_scores_to_db(scored: list[dict], target_date: date) -> dict:
    """
    Save a batch of scored stocks into the `scores` table.

    Each row stores all 8 sub-scores plus the horizon used. Uses
    ON CONFLICT(stock_id, date) so daily re-runs replace old scores
    rather than creating duplicates.

    Note: re-running with a different horizon will OVERWRITE the prior
    score for the same stock+date. If you want to keep multiple horizons
    side-by-side later, the schema's UNIQUE constraint would need to
    include `horizon`.

    Args:
        scored:      list of dicts from score_all_stocks().
        target_date: the trading day these scores are for.

    Returns:
        Dict with counts: {'saved': N, 'skipped': N}.
    """
    saved   = 0
    skipped = 0

    conn = get_connection()
    try:
        for s in scored:
            # Skip stocks that had absolutely no usable signals.
            if s["composite_score"] is None:
                skipped += 1
                continue

            conn.execute(
                """
                INSERT INTO scores
                    (stock_id, date, composite_score,
                     position_score, volume_score,
                     dividend_score, range_score,
                     roe_score, debt_score,
                     fcf_margin_score, profit_margin_score,
                     horizon, data_completeness, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stock_id, date, horizon) DO UPDATE SET
                    composite_score     = excluded.composite_score,
                    position_score      = excluded.position_score,
                    volume_score        = excluded.volume_score,
                    dividend_score      = excluded.dividend_score,
                    range_score         = excluded.range_score,
                    roe_score           = excluded.roe_score,
                    debt_score          = excluded.debt_score,
                    fcf_margin_score    = excluded.fcf_margin_score,
                    profit_margin_score = excluded.profit_margin_score,
                    horizon             = excluded.horizon,
                    data_completeness   = excluded.data_completeness,
                    notes               = excluded.notes
                """,
                (
                    s["stock_id"],
                    target_date.isoformat(),
                    s["composite_score"],
                    s["position_score"],
                    s["volume_score"],
                    s["dividend_score"],
                    s["range_score"],
                    s["roe_score"],
                    s["debt_score"],
                    s["fcf_margin_score"],
                    s["profit_margin_score"],
                    s["horizon"],
                    s["data_completeness"],
                    s["notes"],
                ),
            )
            saved += 1

        conn.commit()
    finally:
        conn.close()

    log.info(
        "Scores saved: %d rows for %s (skipped %d).",
        saved, target_date.isoformat(), skipped
    )
    return {"saved": saved, "skipped": skipped}
# ---------------------------------------------------------------------------
# Read scores back from the database for display
# ---------------------------------------------------------------------------
def get_latest_rankings(
    limit: int = 25,
    horizon: str = DEFAULT_HORIZON,
) -> dict:
    """
    Fetch the most recent day's rankings for a given horizon.

    Looks at the most recent date for which scores exist matching this
    horizon, then splits results into main and incomplete-data lists
    based on MAIN_RANKING_THRESHOLD.

    Args:
        limit:   max number of stocks to return per list.
        horizon: which horizon to fetch (one of HORIZON_WEIGHTS keys).

    Returns:
        Dict with:
            date:             ISO date string (or None if no scores)
            horizon:          the horizon used
            main:             list of top-N main ranking stocks
            incomplete:       list of top-N incomplete-data stocks
            total_main:       total count in main ranking
            total_incomplete: total count in incomplete
    """
    if horizon not in HORIZON_WEIGHTS:
        log.warning("Unknown horizon '%s', falling back to default.", horizon)
        horizon = DEFAULT_HORIZON

    conn = get_connection()
    try:
        # Find the most recent date for which we have scores for this horizon.
        latest_row = conn.execute(
            "SELECT MAX(date) AS latest FROM scores WHERE horizon = ?",
            (horizon,),
        ).fetchone()

        if not latest_row or not latest_row["latest"]:
            return {
                "date":             None,
                "horizon":          horizon,
                "main":             [],
                "incomplete":       [],
                "total_main":       0,
                "total_incomplete": 0,
            }

        latest_date = latest_row["latest"]

        rows = conn.execute(
            """
            SELECT
                s.symbol,
                s.name,
                s.market,
                sc.composite_score,
                sc.position_score,
                sc.volume_score,
                sc.dividend_score,
                sc.range_score,
                sc.roe_score,
                sc.debt_score,
                sc.fcf_margin_score,
                sc.profit_margin_score,
                sc.data_completeness,
                sc.horizon,
                sc.notes,
                p.close_price,
                p.volume
            FROM scores sc
            JOIN stocks s        ON s.id = sc.stock_id
            LEFT JOIN prices_daily p
                ON p.stock_id = sc.stock_id AND p.date = sc.date
            WHERE sc.date = ? AND sc.horizon = ?
            ORDER BY sc.composite_score DESC
            """,
            (latest_date, horizon),
        ).fetchall()

    finally:
        conn.close()

    all_rows = [dict(r) for r in rows]

    main = [r for r in all_rows
            if r["data_completeness"] is not None
            and r["data_completeness"] >= MAIN_RANKING_THRESHOLD]

    incomplete = [r for r in all_rows
                  if r["data_completeness"] is None
                  or r["data_completeness"] < MAIN_RANKING_THRESHOLD]

    return {
        "date":             latest_date,
        "horizon":          horizon,
        "main":             main[:limit],
        "incomplete":       incomplete[:limit],
        "total_main":       len(main),
        "total_incomplete": len(incomplete),
    }