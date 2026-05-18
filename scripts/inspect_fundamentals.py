import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "jsedge.db"

print("=== Current fundamentals rows ===")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
rows = cur.execute("""
    SELECT s.symbol, f.period_end_date, f.period_type,
           f.eps, f.dividend_per_share,
           f.total_equity, f.shares_outstanding,
           f.net_income, f.revenue,
           SUBSTR(f.notes, 1, 80) AS notes_preview
    FROM fundamentals f JOIN stocks s ON s.id = f.stock_id
    ORDER BY s.symbol, f.period_end_date
""").fetchall()
for r in rows:
    print(dict(r))
print(f"\nTotal rows: {len(rows)}")
conn.close()