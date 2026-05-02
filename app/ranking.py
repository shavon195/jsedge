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


# ---------------------------------------------------------------------------
# Configuration — scoring weights and thresholds
# ---------------------------------------------------------------------------
WEIGHTS = {
    "position":  0.30,
    "volume":    0.25,
    "dividend":  0.25,
    "range":     0.20,
}

# Stocks need at least this fraction of signals with valid data to qualify
# for the main ranking. Below this, they go into the "incomplete" list.
MAIN_RANKING_THRESHOLD = 0.75

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
# Composite score — combines all 4 sub-scores
# ---------------------------------------------------------------------------
def compute_composite_score(
    sub_scores: dict[str, Optional[float]],
) -> dict:
    """
    Combine sub-scores into a single weighted composite, tracking which
    signals had data and which were missing.

    Sub-scores that are None are EXCLUDED from the weighted average — we
    don't penalize a stock for missing data here; that's tracked separately
    via data_completeness so the caller can decide which list it belongs in.

    Args:
        sub_scores: dict with keys 'position', 'volume', 'dividend', 'range'.
                    Each value is a score 0-100, or None if data missing.

    Returns:
        Dict with:
            composite_score:   0-100 weighted average of available signals
            data_completeness: 0.0-1.0 fraction of signals that had data
            missing_signals:   list of signal names that were None
    """
    weighted_sum = 0.0
    used_weight  = 0.0
    missing      = []

    for signal, score in sub_scores.items():
        weight = WEIGHTS.get(signal, 0)

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
        }

    # Normalize: divide by used_weight so missing signals don't drag the
    # score toward zero. A stock with 1 perfect signal still scores 100.
    composite = weighted_sum / used_weight

    # Completeness = fraction of total weight we had data for.
    completeness = used_weight / sum(WEIGHTS.values())

    return {
        "composite_score":   round(composite, 2),
        "data_completeness": round(completeness, 2),
        "missing_signals":   missing,
    }


# ---------------------------------------------------------------------------
# Score every stock for a given date
# ---------------------------------------------------------------------------
def score_all_stocks(target_date: date) -> list[dict]:
    """
    Compute composite scores for every stock that has price data on the
    given date.

    Pulls today's prices, today's range, and 52-week range from the database
    (joined across stocks + prices_daily). Computes 4 sub-scores per stock,
    combines into composite, and returns a list ranked best -> worst.

    Args:
        target_date: the trading day to score.

    Returns:
        List of dicts, sorted descending by composite_score. Each dict has:
            stock_id, symbol, name, market, composite_score,
            position_score, volume_score, dividend_score, range_score,
            data_completeness, missing_signals (list), notes (str)
    """
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
            "Scoring stocks for %s — comparing against %d volumes.",
            target_date.isoformat(), len(volumes_today),
        )

        # Second pass: pull every stock with its price + range data for the date.
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
                p.div_curr_year
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
        # Compute all 4 sub-scores from the row data.
        position_score = compute_position_score(
            r["close_price"], r["week52_range"]
        )
        volume_score   = compute_volume_score(
            r["volume"], volumes_today
        )
        dividend_score = compute_dividend_score(
            r["close_price"], r["div_prev_year"], r["div_curr_year"]
        )
        range_score    = compute_range_score(
            r["close_price"], r["todays_range"]
        )

        sub_scores = {
            "position": position_score,
            "volume":   volume_score,
            "dividend": dividend_score,
            "range":    range_score,
        }

        result = compute_composite_score(sub_scores)

        # Build notes string for incomplete-data stocks.
        notes = None
        if result["missing_signals"]:
            notes = "missing: " + ", ".join(result["missing_signals"])

        results.append({
            "stock_id":          r["stock_id"],
            "symbol":            r["symbol"],
            "name":              r["name"],
            "market":            r["market"],
            "composite_score":   result["composite_score"],
            "position_score":    position_score,
            "volume_score":      volume_score,
            "dividend_score":    dividend_score,
            "range_score":       range_score,
            "data_completeness": result["data_completeness"],
            "notes":             notes,
        })

    # Sort by composite score (None goes last, then descending).
    results.sort(
        key=lambda x: (x["composite_score"] is None, -(x["composite_score"] or 0))
    )

    log.info("Scored %d stocks for %s.", len(results), target_date.isoformat())
    return results

# ---------------------------------------------------------------------------
# Persist scores to the database
# ---------------------------------------------------------------------------
def save_scores_to_db(scored: list[dict], target_date: date) -> dict:
    """
    Save a batch of scored stocks into the `scores` table.

    Uses ON CONFLICT(stock_id, date) so daily re-runs replace old scores
    rather than creating duplicates.

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
                     data_completeness, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stock_id, date) DO UPDATE SET
                    composite_score   = excluded.composite_score,
                    position_score    = excluded.position_score,
                    volume_score      = excluded.volume_score,
                    dividend_score    = excluded.dividend_score,
                    range_score       = excluded.range_score,
                    data_completeness = excluded.data_completeness,
                    notes             = excluded.notes
                """,
                (
                    s["stock_id"],
                    target_date.isoformat(),
                    s["composite_score"],
                    s["position_score"],
                    s["volume_score"],
                    s["dividend_score"],
                    s["range_score"],
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
def get_latest_rankings(limit: int = 25) -> dict:
    """
    Fetch the most recent day's rankings from the scores table.

    Splits results into main and incomplete-data lists based on the
    same MAIN_RANKING_THRESHOLD used by the scorer.

    Args:
        limit: max number of stocks to return per list. Default 25.

    Returns:
        Dict with:
            date:        the date these rankings are from (str, ISO format)
            main:        list of top N stocks with full enough data
            incomplete:  list of top N stocks with incomplete data
            total_main:  total count in main ranking (before limit)
            total_incomplete: total count in incomplete (before limit)
    """
    conn = get_connection()
    try:
        # Find the most recent date we have scores for.
        latest_row = conn.execute(
            "SELECT MAX(date) AS latest FROM scores"
        ).fetchone()

        if not latest_row or not latest_row["latest"]:
            return {
                "date": None,
                "main": [],
                "incomplete": [],
                "total_main": 0,
                "total_incomplete": 0,
            }

        latest_date = latest_row["latest"]

        # Pull all stocks scored on that date, joined with stock info
        # and that day's price.
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
                sc.data_completeness,
                sc.notes,
                p.close_price,
                p.volume
            FROM scores sc
            JOIN stocks s        ON s.id = sc.stock_id
            LEFT JOIN prices_daily p
                ON p.stock_id = sc.stock_id AND p.date = sc.date
            WHERE sc.date = ?
            ORDER BY sc.composite_score DESC
            """,
            (latest_date,),
        ).fetchall()

    finally:
        conn.close()

    # Convert sqlite Row objects to plain dicts so the template can use them.
    all_rows = [dict(r) for r in rows]

    main = [r for r in all_rows
            if r["data_completeness"] is not None
            and r["data_completeness"] >= MAIN_RANKING_THRESHOLD]

    incomplete = [r for r in all_rows
                  if r["data_completeness"] is None
                  or r["data_completeness"] < MAIN_RANKING_THRESHOLD]

    return {
        "date":             latest_date,
        "main":             main[:limit],
        "incomplete":       incomplete[:limit],
        "total_main":       len(main),
        "total_incomplete": len(incomplete),
    }