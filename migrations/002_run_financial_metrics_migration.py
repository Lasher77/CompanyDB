#!/usr/bin/env python3
"""
Run database migration to add financial metrics columns and populate them
from existing full_record JSONB data.

For 5M+ records, this uses batch processing to avoid memory issues.
"""
import sys
import time
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine, text
from app.config import settings


def run_migration():
    """Execute the migration to add financial metrics columns."""
    print("Connecting to database...")
    engine = create_engine(settings.database_url_sync)

    migration_file = Path(__file__).parent / "002_add_financial_metrics.sql"

    try:
        with engine.connect() as conn:
            # Step 1: Add columns and indexes
            print(f"Reading migration from {migration_file}")
            with open(migration_file, 'r') as f:
                sql = f.read()

            print("Step 1/2: Adding columns and indexes...")
            conn.execute(text(sql))
            conn.commit()
            print("  - Added: employee_count, last_revenue columns")
            print("  - Created: partial indexes for fast filtering")

            # Step 2: Populate from existing data in batches
            print("\nStep 2/2: Populating from existing data...")
            print("  This may take a while for large datasets...")

            # Count total records
            result = conn.execute(text("SELECT COUNT(*) FROM company"))
            total = result.scalar()
            print(f"  Total records: {total:,}")

            # Update in batches of 50,000 using JSONB path extraction
            batch_size = 50000
            updated = 0
            start_time = time.time()

            # Use a more efficient UPDATE with subquery
            # Note: Cast to double precision first, then to integer to handle "4.0" format
            update_sql = text("""
                UPDATE company
                SET
                    employee_count = (
                        SELECT ((item->>'value')::double precision)::integer
                        FROM jsonb_array_elements(
                            CASE
                                WHEN full_record->'financials' IS NOT NULL
                                     AND jsonb_typeof(full_record->'financials') = 'object'
                                THEN full_record->'financials'->'items'
                                ELSE '[]'::jsonb
                            END
                        ) AS item
                        WHERE item->>'id' = 'Employees'
                        LIMIT 1
                    ),
                    last_revenue = (
                        SELECT (item->>'value')::double precision
                        FROM jsonb_array_elements(
                            CASE
                                WHEN full_record->'financials' IS NOT NULL
                                     AND jsonb_typeof(full_record->'financials') = 'object'
                                THEN full_record->'financials'->'items'
                                ELSE '[]'::jsonb
                            END
                        ) AS item
                        WHERE item->>'id' = 'Revenue'
                        LIMIT 1
                    )
                WHERE id > :start_id AND id <= :end_id
            """)

            # Get ID range
            result = conn.execute(text("SELECT MIN(id), MAX(id) FROM company"))
            min_id, max_id = result.fetchone()

            if min_id is None:
                print("  No records to update")
                return

            current_id = min_id - 1
            while current_id < max_id:
                end_id = current_id + batch_size
                conn.execute(update_sql, {"start_id": current_id, "end_id": end_id})
                conn.commit()

                current_id = end_id
                updated = min(current_id - min_id + 1, total)
                elapsed = time.time() - start_time
                rate = updated / elapsed if elapsed > 0 else 0
                eta = (total - updated) / rate if rate > 0 else 0

                print(f"\r  Progress: {updated:,}/{total:,} ({100*updated/total:.1f}%) - "
                      f"{rate:.0f} records/sec - ETA: {eta/60:.1f} min", end="", flush=True)

            print()  # New line after progress

            # Count how many records have data
            result = conn.execute(text(
                "SELECT COUNT(*) FROM company WHERE employee_count IS NOT NULL OR last_revenue IS NOT NULL"
            ))
            with_data = result.scalar()

            elapsed = time.time() - start_time
            print(f"\n Migration completed successfully!")
            print(f"  - Total time: {elapsed/60:.1f} minutes")
            print(f"  - Records with financial data: {with_data:,} ({100*with_data/total:.1f}%)")

    except Exception as e:
        print(f"\n Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_migration()
