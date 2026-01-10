#!/usr/bin/env python3
"""
Reset database: Drop all tables and recreate them with the current schema.
Use this when model changes require schema updates.
"""
import sys
import os

# Add the app to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app.database import sync_engine, Base
from app.models import Company, Person, CompanyPerson, ImportJob  # Import all models


def reset_database():
    print("Connecting to database...")

    with sync_engine.connect() as conn:
        # Check connection
        result = conn.execute(text("SELECT current_database()"))
        db_name = result.scalar()
        print(f"Connected to database: {db_name}")

        # List existing tables
        result = conn.execute(text("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
        """))
        tables = [row[0] for row in result]
        print(f"Existing tables: {tables}")

        if tables:
            print("\nDropping all tables...")
            # Drop tables with CASCADE to handle foreign keys
            conn.execute(text("DROP TABLE IF EXISTS company_person CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS company CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS person CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS import_job CASCADE"))
            conn.commit()
            print("Tables dropped.")
        else:
            print("No tables found.")

    # Recreate tables
    print("\nCreating tables with new schema...")
    Base.metadata.create_all(sync_engine)

    # Verify
    with sync_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
        """))
        tables = [row[0] for row in result]
        print(f"Created tables: {tables}")

        # Show company columns
        result = conn.execute(text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'company'
            ORDER BY ordinal_position
        """))
        print("\nCompany table columns:")
        for row in result:
            print(f"  - {row[0]}: {row[1]}")

    print("\nDatabase reset complete!")


if __name__ == "__main__":
    reset_database()
