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

print()
print("=== 138SL detail ===")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
r = conn.execute("""
    SELECT f.eps, f.dividend_per_share,
           f.total_equity, f.shares_outstanding,
           f.net_income, f.revenue
    FROM fundamentals f
    JOIN stocks s ON s.id = f.stock_id
    WHERE s.symbol = '138SL'
""").fetchone()
print(dict(r))

# Also check what type each value is (None vs 0 vs 0.0 matters)
print()
print("=== Types ===")
for k, v in dict(r).items():
    print(f"  {k:<22} value={v!r:<20} type={type(v).__name__}")
conn.close()

print()
print("=== Compare 138SL: live DB vs backup ===")
for label, db_path in [("LIVE", DB_PATH), ("BACKUP", DB_PATH.parent / "jsedge.db.bak-before-v3")]:
    if not db_path.exists():
        print(f"  {label}: file not found")
        continue
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    r = c.execute("""
        SELECT eps, net_income, revenue, total_equity
        FROM fundamentals
        WHERE stock_id = (SELECT id FROM stocks WHERE symbol = '138SL')
    """).fetchone()
    print(f"  {label}: {dict(r) if r else None}")
    c.close()