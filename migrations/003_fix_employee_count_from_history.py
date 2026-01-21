#!/usr/bin/env python3
"""
Fix employee_count extraction by also searching in history.financials.

The original migration (002) only looked in record['financials']['items'],
but employee data is often stored in record['history']['financials'][n]['items'].

This script updates employee_count from historical financials for records
where it's still NULL.
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
    """Extract employee_count from history.financials for records where it's NULL."""
    print("Connecting to database...")
    engine = create_engine(settings.database_url_sync)

    try:
        with engine.connect() as conn:
            # Count records needing update
            result = conn.execute(text(
                "SELECT COUNT(*) FROM company WHERE employee_count IS NULL"
            ))
            null_count = result.scalar()
            print(f"Records with NULL employee_count: {null_count:,}")

            if null_count == 0:
                print("No records need updating.")
                return

            print("\nUpdating employee_count from history.financials...")
            print("This searches historical financial data for employee counts.")

            # Get total records for progress
            result = conn.execute(text("SELECT COUNT(*) FROM company"))
            total = result.scalar()

            # Update in batches using JSONB path extraction from history.financials
            # This SQL extracts the employee count from the most recent historical entry
            batch_size = 50000
            start_time = time.time()

            # The SQL extracts employee count from history->financials array
            # It finds the first 'Employees' item across all financial entries
            # (entries are typically already sorted by date in the source data)
            update_sql = text("""
                UPDATE company
                SET employee_count = subq.emp_count
                FROM (
                    SELECT c.id, (
                        SELECT ((item->>'value')::double precision)::integer
                        FROM jsonb_array_elements(
                            full_record->'history'->'financials'
                        ) AS fin_entry,
                        jsonb_array_elements(fin_entry->'items') AS item
                        WHERE item->>'id' = 'Employees'
                          AND item->>'value' IS NOT NULL
                        ORDER BY fin_entry->>'date' DESC
                        LIMIT 1
                    ) AS emp_count
                    FROM company c
                    WHERE c.id > :start_id AND c.id <= :end_id
                      AND c.employee_count IS NULL
                      AND c.full_record->'history'->'financials' IS NOT NULL
                ) AS subq
                WHERE company.id = subq.id
                  AND subq.emp_count IS NOT NULL
            """)

            # Get ID range
            result = conn.execute(text("SELECT MIN(id), MAX(id) FROM company"))
            min_id, max_id = result.fetchone()

            if min_id is None:
                print("No records to update")
                return

            current_id = min_id - 1
            total_updated = 0

            while current_id < max_id:
                end_id = current_id + batch_size
                result = conn.execute(update_sql, {"start_id": current_id, "end_id": end_id})
                batch_updated = result.rowcount
                total_updated += batch_updated
                conn.commit()

                current_id = end_id
                processed = min(current_id - min_id + 1, total)
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (total - processed) / rate if rate > 0 else 0

                print(f"\r  Progress: {processed:,}/{total:,} ({100*processed/total:.1f}%) - "
                      f"Updated: {total_updated:,} - "
                      f"{rate:.0f} records/sec - ETA: {eta/60:.1f} min", end="", flush=True)

            print()  # New line after progress

            # Count remaining NULL values
            result = conn.execute(text(
                "SELECT COUNT(*) FROM company WHERE employee_count IS NULL"
            ))
            still_null = result.scalar()

            # Count total with employee_count
            result = conn.execute(text(
                "SELECT COUNT(*) FROM company WHERE employee_count IS NOT NULL"
            ))
            with_data = result.scalar()

            elapsed = time.time() - start_time
            print(f"\nMigration completed!")
            print(f"  - Total time: {elapsed/60:.1f} minutes")
            print(f"  - Records updated: {total_updated:,}")
            print(f"  - Records with employee_count: {with_data:,} ({100*with_data/total:.1f}%)")
            print(f"  - Records still NULL: {still_null:,} (no employee data in source)")

    except Exception as e:
        print(f"\nMigration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_migration()
