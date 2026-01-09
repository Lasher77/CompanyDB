#!/usr/bin/env python3
"""
Setup script for CompanyDB.
Creates database tables and OpenSearch indices.

Usage:
    python scripts/setup_db.py [--reset]

Options:
    --reset    Drop and recreate all tables/indices (DELETES ALL DATA!)
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from sqlalchemy import create_engine, text
from app.config import settings
from app.database import Base, sync_engine
from app.models import ImportJob, Company, Person, CompanyPerson
from app.opensearch_client import (
    get_opensearch_client,
    init_opensearch_indices,
    COMPANY_INDEX,
    PERSON_INDEX
)


def check_postgres():
    """Check PostgreSQL connection."""
    print("Checking PostgreSQL connection...")
    try:
        engine = create_engine(settings.database_url_sync)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"  ✓ PostgreSQL connected: {version[:50]}...")
            return True
    except Exception as e:
        print(f"  ✗ PostgreSQL error: {e}")
        return False


def check_opensearch():
    """Check OpenSearch connection."""
    print("Checking OpenSearch connection...")
    try:
        client = get_opensearch_client()
        info = client.info()
        print(f"  ✓ OpenSearch connected: {info['version']['number']} ({info['cluster_name']})")
        return True
    except Exception as e:
        print(f"  ✗ OpenSearch error: {e}")
        return False


def setup_postgres(reset=False):
    """Create PostgreSQL tables."""
    print("\nSetting up PostgreSQL tables...")

    if reset:
        print("  Dropping existing tables...")
        Base.metadata.drop_all(sync_engine)

    print("  Creating tables...")
    Base.metadata.create_all(sync_engine)

    # List created tables
    from sqlalchemy import inspect
    inspector = inspect(sync_engine)
    tables = inspector.get_table_names()
    print(f"  ✓ Tables created: {', '.join(tables)}")


def setup_opensearch(reset=False):
    """Create OpenSearch indices."""
    print("\nSetting up OpenSearch indices...")

    client = get_opensearch_client()

    if reset:
        print("  Deleting existing indices...")
        for index in [COMPANY_INDEX, PERSON_INDEX]:
            if client.indices.exists(index):
                client.indices.delete(index)
                print(f"    Deleted: {index}")

    print("  Creating indices...")
    init_opensearch_indices(client)

    # List indices
    indices = list(client.indices.get_alias().keys())
    our_indices = [i for i in indices if i in [COMPANY_INDEX, PERSON_INDEX]]
    print(f"  ✓ Indices created: {', '.join(our_indices)}")


def main():
    reset = "--reset" in sys.argv

    if reset:
        print("=" * 50)
        print("WARNING: --reset flag detected!")
        print("This will DELETE ALL DATA in the database!")
        print("=" * 50)
        confirm = input("Type 'yes' to continue: ")
        if confirm.lower() != 'yes':
            print("Aborted.")
            sys.exit(1)

    print("\n" + "=" * 50)
    print("CompanyDB Setup")
    print("=" * 50)

    # Check connections
    pg_ok = check_postgres()
    os_ok = check_opensearch()

    if not pg_ok or not os_ok:
        print("\n✗ Cannot proceed - fix connection issues first.")
        print("\nTips:")
        print("  - PostgreSQL: Check if service is running (pg_isready -h localhost)")
        print("  - OpenSearch: Check if service is running (curl localhost:9200)")
        print("  - Check .env file for correct connection settings")
        sys.exit(1)

    # Setup
    setup_postgres(reset)
    setup_opensearch(reset)

    print("\n" + "=" * 50)
    print("✓ Setup complete!")
    print("=" * 50)
    print("\nNext steps:")
    print("  1. Start the backend: uvicorn app.main:app --reload")
    print("  2. Check health: curl http://localhost:8000/health")
    print("  3. Start import: curl -X POST http://localhost:8000/imports \\")
    print('       -H "Content-Type: application/json" \\')
    print('       -d \'{"filename": "export2025Q3-DE-XL-de-X.jsonl"}\'')


if __name__ == "__main__":
    main()
