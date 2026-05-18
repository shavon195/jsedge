"""
JSEdge — Recovery script: restore 138SL's lost income-statement values.

Context:
    When 138SL was saved via the edit form on 2026-05-18, the form was
    missing income-statement inputs (template bug). The save route wrote
    NULL into eps, net_income, revenue, operating_income, and several other
    fields — destroying the originals.

    This script reads 138SL's row from the pre-v3 backup file and writes
    the lost values back into the live DB. dividend_per_share (the value
    Shavon intentionally entered as 0) is preserved.

Safe to run multiple times — uses targeted UPDATE only.
"""

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
LIVE_DB   = PROJECT_ROOT / "data" / "jsedge.db"
BACKUP_DB = PROJECT_ROOT / "data" / "jsedge.db.bak-before-v3"

# These are the columns the edit form's Save would have nulled out
# because their inputs were missing from the template.
RECOVER_COLS = [
    "eps",
    "net_income",
    "operating_income",
    "revenue",
    "total_assets",
    "operating_cash_flow",
    "free_cash_flow",
]


def main():
    if not BACKUP_DB.exists():
        raise SystemExit(f"Backup not found at {BACKUP_DB}")

    # Pull 138SL's pre-loss values from the backup.
    backup = sqlite3.connect(BACKUP_DB)
    backup.row_factory = sqlite3.Row
    bak_row = backup.execute("""
        SELECT f.*
        FROM fundamentals f
        JOIN stocks s ON s.id = f.stock_id
        WHERE s.symbol = '138SL'
    """).fetchone()
    backup.close()

    if bak_row is None:
        raise SystemExit("No 138SL row in backup. Cannot recover.")

    print("=== Backup row found ===")
    for col in RECOVER_COLS:
        print(f"  {col:<22} = {bak_row[col]!r}")

    # Pull 138SL's current live state for comparison.
    live = sqlite3.connect(LIVE_DB)
    live.row_factory = sqlite3.Row
    live_row = live.execute("""
        SELECT f.id, f.dividend_per_share,
               f.eps, f.net_income, f.operating_income, f.revenue,
               f.total_assets, f.operating_cash_flow, f.free_cash_flow
        FROM fundamentals f
        JOIN stocks s ON s.id = f.stock_id
        WHERE s.symbol = '138SL'
    """).fetchone()

    if live_row is None:
        raise SystemExit("No 138SL row in live DB. Cannot recover.")

    print()
    print("=== Live row before recovery ===")
    for col in RECOVER_COLS:
        print(f"  {col:<22} = {live_row[col]!r}")
    print(f"  dividend_per_share     = {live_row['dividend_per_share']!r}  (KEEP — Shavon entered this)")

    # Build the UPDATE.
    set_clauses = ", ".join(f"{c} = ?" for c in RECOVER_COLS)
    params      = [bak_row[c] for c in RECOVER_COLS] + [live_row["id"]]

    print()
    print("=== Applying UPDATE ===")
    print(f"  UPDATE fundamentals SET {set_clauses}, updated_at = datetime('now') WHERE id = {live_row['id']}")

    live.execute(
        f"UPDATE fundamentals SET {set_clauses}, updated_at = datetime('now') WHERE id = ?",
        params,
    )
    live.commit()

    # Verify.
    verify = live.execute("""
        SELECT eps, dividend_per_share, net_income, operating_income, revenue,
               total_assets, operating_cash_flow, free_cash_flow
        FROM fundamentals
        WHERE id = ?
    """, (live_row["id"],)).fetchone()
    live.close()

    print()
    print("=== Live row AFTER recovery ===")
    for k in verify.keys():
        print(f"  {k:<22} = {verify[k]!r}")

    print()
    print("✅ Recovery complete.")


if __name__ == "__main__":
    main()