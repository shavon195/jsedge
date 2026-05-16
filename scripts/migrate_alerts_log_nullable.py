"""
JSEdge - Migration: make alerts_log.stock_id nullable.

The original schema set stock_id NOT NULL, which blocks alerts that
aren't tied to a specific stock (e.g. keep-alive pings, daily summaries
covering multiple stocks).

This script recreates the table with stock_id nullable, preserves
existing rows, and verifies row counts match before dropping the old
table.

Safe to run multiple times: it checks the current schema first and
exits cleanly if the migration has already been applied.

Usage:
    python scripts/migrate_alerts_log_nullable.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_connection


def is_already_migrated(conn) -> bool:
    """Return True if alerts_log.stock_id already allows NULL."""
    rows = conn.execute("PRAGMA table_info(alerts_log)").fetchall()
    for r in rows:
        if r["name"] == "stock_id":
            return r["notnull"] == 0
    return False


def main() -> None:
    conn = get_connection()
    try:
        if is_already_migrated(conn):
            print("alerts_log.stock_id is already nullable. Nothing to do.")
            return

        # Count existing rows so we can verify the copy succeeded.
        before = conn.execute("SELECT COUNT(*) AS n FROM alerts_log").fetchone()["n"]
        print(f"Migrating alerts_log ({before} existing rows)...")

        # Transaction: rename, recreate, copy, drop.
        conn.execute("BEGIN")

        conn.execute("ALTER TABLE alerts_log RENAME TO alerts_log_old")

        conn.execute("""
            CREATE TABLE alerts_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_id        INTEGER,
                alert_type      TEXT    NOT NULL,
                message_summary TEXT    NOT NULL,
                delivered_via   TEXT,
                sent_at         TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (stock_id) REFERENCES stocks(id) ON DELETE SET NULL
            )
        """)

        conn.execute("""
            INSERT INTO alerts_log
                (id, stock_id, alert_type, message_summary, delivered_via, sent_at)
            SELECT
                id, stock_id, alert_type, message_summary, delivered_via, sent_at
            FROM alerts_log_old
        """)

        after = conn.execute("SELECT COUNT(*) AS n FROM alerts_log").fetchone()["n"]
        if after != before:
            conn.execute("ROLLBACK")
            print(f"ERROR: row count mismatch (before={before}, after={after}). "
                  f"Rolled back.")
            return

        conn.execute("DROP TABLE alerts_log_old")
        conn.execute("COMMIT")

        print(f"Migration complete. {after} rows preserved.")

        # Confirm the new schema.
        rows = conn.execute("PRAGMA table_info(alerts_log)").fetchall()
        for r in rows:
            mark = " (NULLABLE)" if r["notnull"] == 0 else ""
            print(f"  {r['name']:20s} {r['type']}{mark}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()