#!/usr/bin/env python3
"""
Run database migration to add contact fields to company table.
This script can be run directly without needing psql.
"""
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine, text
from app.config import settings

def run_migration():
    """Execute the migration to add contact fields."""
    print("Connecting to database...")
    engine = create_engine(settings.database_url_sync)

    migration_file = Path(__file__).parent / "001_add_contact_fields_to_company.sql"

    try:
        with engine.connect() as conn:
            print(f"Reading migration from {migration_file}")
            with open(migration_file, 'r') as f:
                sql = f.read()

            print("Executing migration...")
            conn.execute(text(sql))
            conn.commit()

            print("✓ Migration completed successfully!")
            print("  - Added: email, website, phone, domain columns to company table")
            print("  - Created: index on domain column")

    except Exception as e:
        print(f"✗ Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migration()
