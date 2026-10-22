#!/usr/bin/env python3
"""Database initialization script to create or reset tables."""

import argparse
from pathlib import Path
import sys

# Ensure backend root is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import inspect
from app.config import get_settings
from app.database import Base, engine
import app.models  # noqa: F401 - registers models with Base.metadata


def init_database(reset: bool = False) -> None:
    """Initialize database tables, optionally dropping them first if requested."""
    settings = get_settings()

    if reset:
        if settings.APP_ENV.lower() == "production":
            print("ERROR: Cannot reset database in production environment (APP_ENV=production).")
            sys.exit(1)

        confirmation = input("WARNING: This will drop ALL tables. Type 'yes' to confirm: ")
        if confirmation.strip().lower() != "yes":
            print("Database reset aborted.")
            return

        print("Dropping all existing tables...")
        Base.metadata.drop_all(bind=engine)
        print("All tables dropped successfully.")

    print(f"Creating database tables on '{settings.DB_NAME}' ({settings.DB_HOST}:{settings.DB_PORT})...")
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    current_tables = inspector.get_table_names()
    print("\nDatabase tables currently present:")
    for table in sorted(current_tables):
        print(f" - {table}")
    print("\nDatabase initialization completed successfully.")


def main():
    parser = argparse.ArgumentParser(description="Initialize database tables for Restaurant OMS.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop all existing tables before recreating them (requires confirmation, blocked in production).",
    )
    args = parser.parse_args()
    init_database(reset=args.reset)


if __name__ == "__main__":
    main()
