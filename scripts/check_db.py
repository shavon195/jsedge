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

conn.close()