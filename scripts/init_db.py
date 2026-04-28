"""
JSEdge — Database initialization script.

Run this once to create the SQLite database with all tables and seed
defaults. Safe to run multiple times — existing tables and data are
preserved (we use IF NOT EXISTS and INSERT OR IGNORE).

Usage:
    python scripts/init_db.py

Run from the project root, with your venv activated.
"""

import sys
from pathlib import Path

# Add the project root to Python's import path so we can import from app/
# This is necessary because we're running this from scripts/ but want to
# pull in app/database.py.
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import initialize_database, DB_PATH


def main() -> None:
    print("=" * 60)
    print("JSEdge — Database initialization")
    print("=" * 60)
    print(f"Target database file: {DB_PATH}")
    print()

    initialize_database()

    print()
    print("All tables created. You can now start using JSEdge.")
    print("=" * 60)


if __name__ == "__main__":
    main()