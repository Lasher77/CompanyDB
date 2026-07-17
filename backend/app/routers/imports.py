import re
import threading
import logging
import io
import csv
from datetime import datetime

# Use orjson for 3-10x faster JSON parsing (especially on Apple Silicon)
try:
    import orjson
    def json_loads(s):
        return orjson.loads(s)
    def json_dumps(obj):
        return orjson.dumps(obj).decode('utf-8')
except ImportError:
    import json
    def json_loads(s):
        return json.loads(s)
    def json_dumps(obj):
        return json.dumps(obj, ensure_ascii=False)
from uuid import UUID
from pathlib import Path
from typing import Dict, Set
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from ..database import get_db, sync_engine
from ..models import ImportJob, Company, Person, CompanyPerson
from ..schemas import ImportFileInfo, ImportJobCreate, ImportJobResponse
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/imports", tags=["imports"])


def human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def extract_domain(url_or_email: str | None) -> str | None:
    """Extract and normalize domain from URL or email address."""
    if not url_or_email:
        return None

    value = url_or_email.lower().strip()

    # Handle email addresses
    if '@' in value:
        value = value.split('@')[1]
    else:
        # Handle URLs - remove protocol
        value = re.sub(r'^https?://', '', value)

    # Remove www. prefix
    value = re.sub(r'^www\.', '', value)

    # Remove path and query string
    value = value.split('/')[0].split('?')[0]

    # Basic validation - should have at least one dot
    if '.' not in value or len(value) < 4:
        return None

    return value


def extract_financial_metrics(record: dict) -> dict:
    """Extract employee count and revenue from NorthData financials.

    Searches in two locations:
    1. record['financials']['items'] - current/latest financials
    2. record['history']['financials'] - historical financials (sorted by date, newest first)
    """
    employee_count = None
    last_revenue = None

    # Helper to extract values from a financials items list
    def extract_from_items(items: list) -> tuple:
        emp = None
        rev = None
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = item.get('id')
            value = item.get('value')

            if item_id == 'Employees' and value is not None and emp is None:
                try:
                    emp = int(value)
                except (ValueError, TypeError):
                    pass
            elif item_id == 'Revenue' and value is not None and rev is None:
                try:
                    rev = float(value)
                except (ValueError, TypeError):
                    pass
        return emp, rev

    # 1. Try current financials first
    financials = record.get('financials')
    if financials and isinstance(financials, dict):
        items = financials.get('items', [])
        employee_count, last_revenue = extract_from_items(items)

    # 2. If not found, search in history.financials (sorted by date descending)
    if employee_count is None or last_revenue is None:
        history = record.get('history', {})
        history_financials = history.get('financials', [])

        if history_financials and isinstance(history_financials, list):
            # Sort by date descending to get most recent first
            sorted_financials = sorted(
                [f for f in history_financials if isinstance(f, dict)],
                key=lambda x: x.get('date', ''),
                reverse=True
            )

            for fin_entry in sorted_financials:
                items = fin_entry.get('items', [])
                hist_emp, hist_rev = extract_from_items(items)

                if employee_count is None and hist_emp is not None:
                    employee_count = hist_emp
                if last_revenue is None and hist_rev is not None:
                    last_revenue = hist_rev

                # Stop if we found both
                if employee_count is not None and last_revenue is not None:
                    break

    return {
        'employee_count': employee_count,
        'last_revenue': last_revenue
    }


def extract_contact_info(record: dict) -> dict:
    """Extract email, website, phone and domain from NorthData record."""
    email = None
    website = None
    phone = None
    domain = None

    extras = record.get('extras', [])
    for extra in extras:
        if not isinstance(extra, dict):
            continue
        items = extra.get('items', [])
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = item.get('id', '').lower()
            value = item.get('value')

            if item_id == 'email' and value:
                email = value
            elif item_id == 'url' and value:
                website = value
            elif item_id == 'phone' and value:
                phone = value

    # Extract domain from website or email
    if website:
        domain = extract_domain(website)
    if not domain and email:
        domain = extract_domain(email)

    return {
        'email': email,
        'website': website,
        'phone': phone,
        'domain': domain
    }


@router.get("/files", response_model=list[ImportFileInfo])
async def list_import_files():
    """List available JSONL files in the data directory."""
    data_dir = settings.data_directory
    if not data_dir.exists():
        return []

    files = []
    for f in data_dir.glob("*.jsonl"):
        stat = f.stat()
        files.append(ImportFileInfo(
            filename=f.name,
            size_bytes=stat.st_size,
            size_human=human_readable_size(stat.st_size)
        ))

    return sorted(files, key=lambda x: x.filename)


@router.post("", response_model=ImportJobResponse)
async def create_import_job(
    job: ImportJobCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Start a new import job for a JSONL file."""
    # Validate file exists
    file_path = settings.data_directory / job.filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {job.filename}")

    if not job.filename.endswith(".jsonl"):
        raise HTTPException(status_code=400, detail="Only .jsonl files are supported")

    # Count total lines (for progress tracking) with error handling
    total_lines = 0
    try:
        # Use binary mode for faster counting, then decode
        with open(file_path, "rb") as f:
            total_lines = sum(1 for _ in f)
        logger.info(f"Counted {total_lines} lines in {job.filename}")
    except Exception as e:
        logger.error(f"Error counting lines in {job.filename}: {e}")
        # Estimate based on file size (assume ~500 bytes per line average)
        try:
            file_size = file_path.stat().st_size
            total_lines = max(1, file_size // 500)
            logger.info(f"Estimated {total_lines} lines based on file size {file_size}")
        except:
            total_lines = 1  # Fallback

    # Create import job record
    import_job = ImportJob(
        filename=job.filename,
        status="pending",
        total_lines=total_lines
    )
    db.add(import_job)
    await db.commit()
    await db.refresh(import_job)

    # Start background import in a separate thread (to not block async loop)
    thread = threading.Thread(target=run_import_job_fast, args=(import_job.id, file_path))
    thread.start()

    return import_job


@router.get("/{job_id}", response_model=ImportJobResponse)
async def get_import_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get status of an import job."""
    result = await db.execute(select(ImportJob).where(ImportJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job


@router.get("", response_model=list[ImportJobResponse])
async def list_import_jobs(db: AsyncSession = Depends(get_db)):
    """List all import jobs."""
    result = await db.execute(select(ImportJob).order_by(ImportJob.created_at.desc()))
    return result.scalars().all()


@router.delete("/{job_id}")
async def cancel_import_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """Cancel/delete an import job. Use this to stop stuck imports."""
    result = await db.execute(select(ImportJob).where(ImportJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")

    old_status = job.status

    # Mark as cancelled or delete
    if job.status in ("pending", "running"):
        job.status = "cancelled"
        job.error_message = "Cancelled by user"
        job.updated_at = datetime.utcnow()
        await db.commit()
        return {"message": f"Job {job_id} cancelled (was {old_status})"}
    else:
        # Job already completed/failed - delete it
        await db.delete(job)
        await db.commit()
        return {"message": f"Job {job_id} deleted (was {old_status})"}


def escape_copy_value(value) -> str:
    """Escape a value for PostgreSQL COPY format."""
    if value is None:
        return "\\N"
    if isinstance(value, bool):
        return "t" if value else "f"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        # JSON - escape backslashes and tabs
        s = json_dumps(value)
        return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
    # String - escape special chars
    s = str(value)
    return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def run_import_job_fast(job_id: UUID, file_path: Path):
    """Ultra-fast upsert import using PostgreSQL COPY into staging tables.

    The file is streamed via COPY into per-job UNLOGGED staging tables, then
    merged into the live tables with INSERT ... ON CONFLICT DO UPDATE:
    - New companies/persons are inserted.
    - Existing companies/persons are updated with the data from the file
      (NorthData exports always contain the full current state incl. history).
    - Company-person relationships of every company in the file are replaced,
      so e.g. resigned managing directors disappear.
    """
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=sync_engine)

    # Initialize variables for cleanup in except block
    raw_conn = None
    cursor = None

    # Per-job staging table names so concurrent jobs cannot clash
    suffix = job_id.hex
    stg_company = f"staging_company_{suffix}"
    stg_person = f"staging_person_{suffix}"
    stg_rel = f"staging_company_person_{suffix}"

    def drop_staging_tables(cur, conn):
        cur.execute(f"DROP TABLE IF EXISTS {stg_company}, {stg_person}, {stg_rel}")
        conn.commit()

    with SessionLocal() as db:
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if not job:
            return

        # Check if job was cancelled before starting
        if job.status == "cancelled":
            logger.info(f"Import job {job_id} was cancelled, skipping")
            return

        # Don't restart completed or failed jobs
        if job.status in ("completed", "failed"):
            logger.info(f"Import job {job_id} already {job.status}, skipping")
            return

        job.status = "running"
        job.updated_at = datetime.utcnow()
        db.commit()

        try:
            # Get raw PostgreSQL connection for COPY
            raw_conn = sync_engine.raw_connection()
            cursor = raw_conn.cursor()

            # Create staging tables (UNLOGGED = no WAL = fast)
            logger.info("Creating staging tables...")
            cursor.execute(f"DROP TABLE IF EXISTS {stg_company}, {stg_person}, {stg_rel}")
            cursor.execute(f"""
                CREATE UNLOGGED TABLE {stg_company} (
                    import_job_id UUID,
                    company_id TEXT,
                    raw_name TEXT,
                    legal_name TEXT,
                    legal_form TEXT,
                    status TEXT,
                    terminated BOOLEAN,
                    register_unique_key TEXT,
                    register_id TEXT,
                    address_city TEXT,
                    address_postal_code TEXT,
                    address_country TEXT,
                    email TEXT,
                    website TEXT,
                    phone TEXT,
                    domain TEXT,
                    employee_count INTEGER,
                    last_revenue DOUBLE PRECISION,
                    last_update_time TIMESTAMPTZ,
                    full_record JSONB,
                    created_at TIMESTAMPTZ
                )
            """)
            cursor.execute(f"""
                CREATE UNLOGGED TABLE {stg_person} (
                    person_id TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    birth_year INTEGER,
                    address_city TEXT,
                    full_record JSONB,
                    created_at TIMESTAMPTZ
                )
            """)
            cursor.execute(f"""
                CREATE UNLOGGED TABLE {stg_rel} (
                    company_id TEXT,
                    person_id TEXT,
                    role_type TEXT,
                    role_description TEXT
                )
            """)
            raw_conn.commit()

            # Initialize buffers and tracking.
            # Dedup only within the file - existing DB rows get updated, not skipped.
            company_buffer = io.StringIO()
            person_buffer = io.StringIO()
            rel_buffer = io.StringIO()
            seen_company_ids = set()
            seen_person_ids = set()

            # Tracking
            processed = 0
            companies_count = 0
            persons_count = 0
            rel_count = 0
            last_flushed_companies = 0
            batch_size = 50000

            def flush_staging_buffers():
                nonlocal company_buffer, person_buffer, rel_buffer
                if company_buffer.tell() > 0:
                    company_buffer.seek(0)
                    cursor.copy_from(
                        company_buffer, stg_company,
                        columns=('import_job_id', 'company_id', 'raw_name', 'legal_name', 'legal_form',
                                'status', 'terminated', 'register_unique_key', 'register_id',
                                'address_city', 'address_postal_code', 'address_country',
                                'email', 'website', 'phone', 'domain',
                                'employee_count', 'last_revenue',
                                'last_update_time', 'full_record', 'created_at')
                    )
                if person_buffer.tell() > 0:
                    person_buffer.seek(0)
                    cursor.copy_from(
                        person_buffer, stg_person,
                        columns=('person_id', 'first_name', 'last_name', 'birth_year',
                                'address_city', 'full_record', 'created_at')
                    )
                if rel_buffer.tell() > 0:
                    rel_buffer.seek(0)
                    cursor.copy_from(
                        rel_buffer, stg_rel,
                        columns=('company_id', 'person_id', 'role_type', 'role_description')
                    )
                raw_conn.commit()
                company_buffer = io.StringIO()
                person_buffer = io.StringIO()
                rel_buffer = io.StringIO()

            logger.info("Starting streaming into staging tables...")

            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        processed += 1
                        continue

                    try:
                        record = json_loads(line)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"JSON parse error at line {processed}: {e}")
                        processed += 1
                        continue

                    company_id = record.get("id", "")

                    # Skip duplicates within the same file
                    company_id_str = str(company_id)
                    if company_id_str in seen_company_ids:
                        processed += 1
                        continue

                    seen_company_ids.add(company_id_str)

                    # Extract fields
                    name_obj = record.get("name", {})
                    address_obj = record.get("address", {})
                    register_obj = record.get("register", {})

                    # Extract contact info
                    contact_info = extract_contact_info(record)

                    # Extract financial metrics (employee count, revenue)
                    financial_info = extract_financial_metrics(record)

                    # Parse lastUpdateTime
                    last_update_time = None
                    if record.get("lastUpdateTime"):
                        try:
                            last_update_time = datetime.fromisoformat(
                                record["lastUpdateTime"].replace("Z", "+00:00")
                            )
                        except:
                            pass

                    # Build COPY line for company
                    # Columns: import_job_id, company_id, raw_name, legal_name, legal_form, status,
                    #          terminated, register_unique_key, register_id, address_city,
                    #          address_postal_code, address_country, email, website, phone, domain,
                    #          employee_count, last_revenue, last_update_time, full_record, created_at
                    company_line = "\t".join([
                        escape_copy_value(str(job_id)),
                        escape_copy_value(company_id),
                        escape_copy_value(record.get("rawName")),
                        escape_copy_value(name_obj.get("name")),
                        escape_copy_value(name_obj.get("legalForm")),
                        escape_copy_value(record.get("status")),
                        escape_copy_value(record.get("terminated")),
                        escape_copy_value(register_obj.get("uniqueKey")),
                        escape_copy_value(register_obj.get("id")),
                        escape_copy_value(address_obj.get("city")),
                        escape_copy_value(address_obj.get("postalCode")),
                        escape_copy_value(address_obj.get("country")),
                        escape_copy_value(contact_info.get("email")),
                        escape_copy_value(contact_info.get("website")),
                        escape_copy_value(contact_info.get("phone")),
                        escape_copy_value(contact_info.get("domain")),
                        escape_copy_value(financial_info.get("employee_count")),
                        escape_copy_value(financial_info.get("last_revenue")),
                        escape_copy_value(last_update_time),
                        escape_copy_value(record),
                        escape_copy_value(datetime.utcnow()),
                    ])
                    company_buffer.write(company_line + "\n")
                    companies_count += 1

                    # Process related persons
                    related_persons = record.get("relatedPersons", {}).get("items", [])
                    for rp in related_persons:
                        person_data = rp.get("person", {})
                        person_id = person_data.get("id")
                        if not person_id:
                            continue

                        # Relationship goes straight into the staging buffer
                        roles = rp.get("roles", [])
                        role_type = roles[0].get("type") if roles else rp.get("description")
                        role_desc = rp.get("description")
                        rel_line = "\t".join([
                            escape_copy_value(company_id),
                            escape_copy_value(person_id),
                            escape_copy_value(role_type),
                            escape_copy_value(role_desc),
                        ])
                        rel_buffer.write(rel_line + "\n")
                        rel_count += 1

                        # Stage person once per file
                        if person_id not in seen_person_ids:
                            seen_person_ids.add(person_id)

                            person_name = person_data.get("name", {})
                            person_address = person_data.get("address", {})

                            # Build COPY line for person
                            # Columns: person_id, first_name, last_name, birth_year, address_city, full_record, created_at
                            person_line = "\t".join([
                                escape_copy_value(person_id),
                                escape_copy_value(person_name.get("firstName")),
                                escape_copy_value(person_name.get("lastName")),
                                escape_copy_value(person_data.get("birthYear")),
                                escape_copy_value(person_address.get("city")),
                                escape_copy_value(person_data),
                                escape_copy_value(datetime.utcnow()),
                            ])
                            person_buffer.write(person_line + "\n")
                            persons_count += 1

                    processed += 1

                    # Flush buffers periodically
                    if companies_count - last_flushed_companies >= batch_size:
                        last_flushed_companies = companies_count
                        logger.info(f"Flushing batch at {companies_count} companies...")
                        flush_staging_buffers()

                        # Update progress and honor cancellation
                        db.refresh(job)
                        if job.status == "cancelled":
                            logger.info(f"Import job {job_id} cancelled, cleaning up staging tables")
                            drop_staging_tables(cursor, raw_conn)
                            cursor.close()
                            raw_conn.close()
                            return

                        job.processed_lines = processed
                        job.companies_imported = companies_count
                        job.persons_imported = persons_count
                        job.updated_at = datetime.utcnow()
                        db.commit()

                        logger.info(f"Progress: {processed}/{job.total_lines} lines, {companies_count} companies, {persons_count} persons")

            # Final flush into staging
            logger.info("Final staging flush...")
            flush_staging_buffers()
            logger.info(f"Staged: {companies_count} companies, {persons_count} persons, {rel_count} relationships")

            # Free dedup memory before the merge phase
            seen_company_ids = None
            seen_person_ids = None

            # ===== MERGE PHASE =====
            # Give PostgreSQL more memory for the joins/sorts below
            try:
                cursor.execute(f"SET work_mem = '{settings.pg_work_mem}'")
            except Exception as e:
                logger.warning(f"Could not set work_mem: {e}")

            cursor.execute(f"ANALYZE {stg_company}")
            cursor.execute(f"ANALYZE {stg_person}")
            cursor.execute(f"ANALYZE {stg_rel}")

            # Count how many rows will be updates vs. inserts (for logging)
            cursor.execute(f"SELECT COUNT(*) FROM {stg_company} s JOIN company c ON c.company_id = s.company_id")
            companies_updated = cursor.fetchone()[0]
            cursor.execute(f"SELECT COUNT(*) FROM {stg_person} s JOIN person p ON p.person_id = s.person_id")
            persons_updated = cursor.fetchone()[0]
            logger.info(
                f"Merging companies: {companies_count - companies_updated} new, {companies_updated} to update; "
                f"persons: {persons_count - persons_updated} new, {persons_updated} to update"
            )

            # Upsert companies (created_at is kept from the original insert)
            logger.info("Upserting companies...")
            cursor.execute(f"""
                INSERT INTO company (import_job_id, company_id, raw_name, legal_name, legal_form,
                                     status, terminated, register_unique_key, register_id,
                                     address_city, address_postal_code, address_country,
                                     email, website, phone, domain,
                                     employee_count, last_revenue, last_update_time,
                                     full_record, created_at)
                SELECT import_job_id, company_id, raw_name, legal_name, legal_form,
                       status, terminated, register_unique_key, register_id,
                       address_city, address_postal_code, address_country,
                       email, website, phone, domain,
                       employee_count, last_revenue, last_update_time,
                       full_record, created_at
                FROM {stg_company}
                ON CONFLICT (company_id) DO UPDATE SET
                    import_job_id = EXCLUDED.import_job_id,
                    raw_name = EXCLUDED.raw_name,
                    legal_name = EXCLUDED.legal_name,
                    legal_form = EXCLUDED.legal_form,
                    status = EXCLUDED.status,
                    terminated = EXCLUDED.terminated,
                    register_unique_key = EXCLUDED.register_unique_key,
                    register_id = EXCLUDED.register_id,
                    address_city = EXCLUDED.address_city,
                    address_postal_code = EXCLUDED.address_postal_code,
                    address_country = EXCLUDED.address_country,
                    email = EXCLUDED.email,
                    website = EXCLUDED.website,
                    phone = EXCLUDED.phone,
                    domain = EXCLUDED.domain,
                    employee_count = EXCLUDED.employee_count,
                    last_revenue = EXCLUDED.last_revenue,
                    last_update_time = EXCLUDED.last_update_time,
                    full_record = EXCLUDED.full_record
            """)
            raw_conn.commit()
            logger.info("Companies merged")

            # Upsert persons (created_at is kept from the original insert)
            logger.info("Upserting persons...")
            cursor.execute(f"""
                INSERT INTO person (person_id, first_name, last_name, birth_year,
                                    address_city, full_record, created_at)
                SELECT person_id, first_name, last_name, birth_year,
                       address_city, full_record, created_at
                FROM {stg_person}
                ON CONFLICT (person_id) DO UPDATE SET
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    birth_year = EXCLUDED.birth_year,
                    address_city = EXCLUDED.address_city,
                    full_record = EXCLUDED.full_record
            """)
            raw_conn.commit()
            logger.info("Persons merged")

            # Replace relationships for every company contained in the file,
            # so roles that no longer exist (e.g. former managing directors) are removed.
            logger.info("Replacing relationships for imported companies...")
            cursor.execute(f"""
                DELETE FROM company_person cp
                USING company c
                WHERE cp.company_db_id = c.id
                  AND c.company_id IN (SELECT company_id FROM {stg_company})
            """)
            deleted_rels = cursor.rowcount
            cursor.execute(f"""
                INSERT INTO company_person (company_db_id, person_db_id, role_type, role_description, role_date)
                SELECT DISTINCT c.id, p.id, s.role_type, s.role_description, NULL::date
                FROM {stg_rel} s
                JOIN company c ON c.company_id = s.company_id
                JOIN person p ON p.person_id = s.person_id
            """)
            inserted_rels = cursor.rowcount
            raw_conn.commit()
            logger.info(f"Relationships replaced: {deleted_rels} removed, {inserted_rels} inserted")

            # Drop staging tables
            drop_staging_tables(cursor, raw_conn)
            logger.info(
                f"Merge completed: companies {companies_count - companies_updated} new / {companies_updated} updated, "
                f"persons {persons_count - persons_updated} new / {persons_updated} updated"
            )

            # Recreate indexes
            logger.info("Recreating indexes...")
            try:
                # Table names are singular: company, person
                db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_legal_name ON company (legal_name)"))
                db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_raw_name ON company (raw_name)"))
                db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_register_id ON company (register_id)"))
                db.execute(text("CREATE INDEX IF NOT EXISTS ix_person_last_name ON person (last_name)"))
                db.execute(text("CREATE INDEX IF NOT EXISTS ix_person_first_name ON person (first_name)"))
                db.commit()
                logger.info("Indexes recreated successfully")
            except Exception as e:
                logger.warning(f"Could not recreate indexes: {e}")

            # Close PostgreSQL connection
            try:
                cursor.close()
                raw_conn.close()
            except:
                pass

            # Mark job as completed
            job.processed_lines = processed
            job.companies_imported = companies_count
            job.persons_imported = persons_count
            job.status = "completed"
            job.updated_at = datetime.utcnow()
            db.commit()

            logger.info(f"Import completed: {companies_count} companies, {persons_count} persons, {rel_count} relationships")
            logger.info("Run POST /imports/reindex to update OpenSearch")

        except Exception as e:
            logger.error(f"Import failed: {e}", exc_info=True)
            try:
                if raw_conn:
                    raw_conn.rollback()
                if cursor and raw_conn:
                    drop_staging_tables(cursor, raw_conn)
                if cursor:
                    cursor.close()
                if raw_conn:
                    raw_conn.close()
            except:
                pass
            job.status = "failed"
            job.error_message = str(e)
            job.updated_at = datetime.utcnow()
            db.commit()
            raise


def bulk_index(client, actions: list[dict]):
    """Bulk index documents to OpenSearch."""
    if not client or not actions:
        return

    body = []
    for action in actions:
        body.append({"index": {"_index": action["_index"], "_id": action["_id"]}})
        body.append(action["_source"])

    client.bulk(body=body, refresh=False)


@router.post("/reindex")
async def reindex_opensearch():
    """Reindex all existing data from PostgreSQL to OpenSearch."""
    if not settings.opensearch_enabled:
        raise HTTPException(status_code=400, detail="OpenSearch is not enabled")

    # Start reindex in background thread
    thread = threading.Thread(target=run_reindex_fast)
    thread.start()

    return {"status": "started", "message": "Reindexing started in background"}


def run_reindex_fast():
    """Ultra-fast reindex using raw SQL and streaming."""
    import gc  # Garbage collection for memory management

    COMPANY_INDEX = "companies"
    PERSON_INDEX = "persons"

    try:
        from ..opensearch_client import get_opensearch_client, init_opensearch_indices
        os_client = get_opensearch_client()

        # Create indices if they don't exist
        init_opensearch_indices(os_client)
        logger.info("OpenSearch indices initialized")

        # Get raw connection - need autocommit=False for server-side cursors
        raw_conn = sync_engine.raw_connection()
        raw_conn.set_session(autocommit=False)

        # Count companies
        count_cursor = raw_conn.cursor()
        count_cursor.execute("SELECT COUNT(*) FROM company")
        total_companies = count_cursor.fetchone()[0]
        count_cursor.close()
        logger.info(f"Reindexing {total_companies} companies...")

        # Use server-side cursor for streaming
        cursor = raw_conn.cursor(name='reindex_companies')

        cursor.execute("""
            SELECT company_id, raw_name, legal_name, legal_form, status, terminated,
                   register_unique_key, register_id, address_city, address_postal_code,
                   address_country, email, website, domain, employee_count, last_revenue,
                   last_update_time,
                   full_record->'segmentCodes'->'wz' AS wz_codes,
                   full_record->'segmentCodes'->'wz2025' AS wz2025_codes
            FROM company
        """)

        batch_size = 5000
        indexed_count = 0

        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break

            # Build batch
            os_batch = []
            for row in rows:
                # Merge wz and wz2025 codes into a single list for OpenSearch
                wz_codes = row[17] or []  # full_record.segmentCodes.wz
                wz2025_codes = row[18] or []  # full_record.segmentCodes.wz2025
                all_wz = list(set(wz_codes + wz2025_codes)) if (wz_codes or wz2025_codes) else []

                os_batch.append({
                    "_index": COMPANY_INDEX,
                    "_id": row[0],
                    "_source": {
                        "company_id": row[0],
                        "raw_name": row[1],
                        "legal_name": row[2],
                        "legal_form": row[3],
                        "status": row[4],
                        "terminated": row[5],
                        "register_unique_key": row[6],
                        "register_id": row[7],
                        "address_city": row[8],
                        "address_postal_code": row[9],
                        "address_country": row[10],
                        "email": row[11],
                        "website": row[12],
                        "domain": row[13],
                        "employee_count": row[14],
                        "last_revenue": row[15],
                        "last_update_time": row[16].isoformat() if row[16] else None,
                        "segment_codes_wz": all_wz,
                    }
                })

            # Bulk index
            bulk_index(os_client, os_batch)
            indexed_count += len(os_batch)
            logger.info(f"Companies: {indexed_count}/{total_companies}")

            # Cleanup
            del os_batch
            del rows
            gc.collect()

        cursor.close()
        gc.collect()
        logger.info("Companies indexed successfully")

        # Index persons
        logger.info("Indexing persons...")

        count_cursor = raw_conn.cursor()
        count_cursor.execute("SELECT COUNT(*) FROM person")
        total_persons = count_cursor.fetchone()[0]
        count_cursor.close()
        logger.info(f"Reindexing {total_persons} persons...")

        cursor = raw_conn.cursor(name='reindex_persons')
        cursor.execute("""
            SELECT person_id, first_name, last_name, birth_year, address_city
            FROM person
        """)

        indexed_count = 0

        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break

            os_batch = []
            for row in rows:
                full_name = f"{row[1] or ''} {row[2] or ''}".strip()
                os_batch.append({
                    "_index": PERSON_INDEX,
                    "_id": row[0],
                    "_source": {
                        "person_id": row[0],
                        "first_name": row[1],
                        "last_name": row[2],
                        "full_name": full_name,
                        "birth_year": row[3],
                        "address_city": row[4],
                        "company_ids": [],
                        "roles": [],
                    }
                })

            bulk_index(os_client, os_batch)
            indexed_count += len(os_batch)
            logger.info(f"Persons: {indexed_count}/{total_persons}")

            del os_batch
            del rows
            gc.collect()

        cursor.close()
        raw_conn.close()

        # Refresh indices
        logger.info("Refreshing indices...")
        os_client.indices.refresh(index=COMPANY_INDEX)
        os_client.indices.refresh(index=PERSON_INDEX)

        logger.info("Reindex completed successfully!")

    except Exception as e:
        logger.error(f"Reindex failed: {e}", exc_info=True)
        try:
            raw_conn.close()
        except:
            pass
        raise


def run_reindex():
    """Legacy reindex - redirects to fast version."""
    run_reindex_fast()
