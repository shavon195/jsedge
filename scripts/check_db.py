"""Quick database verification — run with: python scripts/check_db.py"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection

conn = get_connection()

main_count = conn.execute(
    "SELECT COUNT(*) FROM stocks WHERE market = 'Main Market'"
).fetchone()[0]

junior_count = conn.execute(
    "SELECT COUNT(*) FROM stocks WHERE market = 'Junior Market'"
).fetchone()[0]

print(f"Main Market:    {main_count} stocks")
print(f"Junior Market:  {junior_count} stocks")
print(f"─────────────────────────────")
print(f"Total:          {main_count + junior_count} stocks")

print("\nSample rows:")
for row in conn.execute("SELECT id, symbol, market FROM stocks ORDER BY id LIMIT 3"):
    print(f"  #{row['id']}: {row['symbol']} ({row['market']})")
for row in conn.execute("SELECT id, symbol, market FROM stocks ORDER BY id DESC LIMIT 3"):
    print(f"  #{row['id']}: {row['symbol']} ({row['market']})")

# Prices summary
print("\n--- Prices Daily ---")
total_prices = conn.execute("SELECT COUNT(*) FROM prices_daily").fetchone()[0]
unique_dates = conn.execute("SELECT COUNT(DISTINCT date) FROM prices_daily").fetchone()[0]
print(f"Total price rows: {total_prices}")
print(f"Unique dates:     {unique_dates}")

# A few sample prices
print("\nSample prices (latest date):")
sample = conn.execute("""
    SELECT s.symbol, s.market, p.date, p.close_price, p.volume
    FROM prices_daily p
    JOIN stocks s ON s.id = p.stock_id
    ORDER BY p.date DESC, s.symbol
    LIMIT 5
""").fetchall()
for row in sample:
    print(f"  {row['symbol']:<8} {row['market']:<14} "
          f"{row['date']}  close=${row['close_price']:<8} vol={row['volume']}")

# Show all columns in the scores table (handy for debugging migrations)

# Volume score sanity check on real JSE data
from app.ranking import compute_volume_score

# Verify new price-extras columns got populated
print("\n--- Price Extras Check ---")
sample = conn.execute("""
    SELECT s.symbol, p.todays_range, p.week52_range,
           p.div_prev_year, p.div_curr_year
    FROM prices_daily p
    JOIN stocks s ON s.id = p.stock_id
    WHERE p.date = '2026-04-28'
      AND s.symbol IN ('138SL', 'NCBFG', 'JBG', 'CCC', 'ASBH')
    ORDER BY s.symbol
""").fetchall()

for r in sample:
    print(
        f"  {r['symbol']:<8} "
        f"today={str(r['todays_range']):<16} "
        f"52w={str(r['week52_range']):<18} "
        f"div_prev={r['div_prev_year']}  div_curr={r['div_curr_year']}"
    )

print("\n--- Volume Score Test (real data) ---")
volumes_today = [r["volume"] for r in conn.execute(
    "SELECT volume FROM prices_daily WHERE date = '2026-04-28' AND volume IS NOT NULL"
).fetchall()]

print(f"  Market sample: {len(volumes_today)} stocks with volume data")

sample_symbols = ['138SL', 'NCBFG', 'JBG', 'AFS', 'BIL', 'AHPC']
results = conn.execute("""
    SELECT s.symbol, p.volume
    FROM prices_daily p JOIN stocks s ON s.id = p.stock_id
    WHERE p.date = '2026-04-28' AND s.symbol IN ({})
""".format(",".join("?" * len(sample_symbols))), sample_symbols).fetchall()

for r in results:
    score = compute_volume_score(r["volume"], volumes_today)
    print(f"  {r['symbol']:<8} vol={r['volume']:>10}   score={score}")

print("\n--- Scores Table Schema ---")
cols = conn.execute("PRAGMA table_info(scores)").fetchall()
for c in cols:
    print(f"  {c['name']:<20} {c['type']}")

conn.close()