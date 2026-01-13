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

    # Count total lines (for progress tracking)
    total_lines = sum(1 for _ in open(file_path, "r", encoding="utf-8"))

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
    """Ultra-fast import using PostgreSQL COPY and streaming."""
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import create_engine
    import psycopg2

    SessionLocal = sessionmaker(bind=sync_engine)

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
            # Initialize OpenSearch if enabled
            if settings.opensearch_enabled:
                try:
                    from ..opensearch_client import get_opensearch_client, init_opensearch_indices
                    os_client = get_opensearch_client()
                    init_opensearch_indices(os_client)
                    logger.info("OpenSearch initialized successfully")
                except Exception as e:
                    logger.warning(f"OpenSearch not available, skipping indexing: {e}")
                    os_client = None

            # OPTIMIZATION 1: Disable auto-commit and use larger batches
            batch_size = 5000  # Increased from 1000

            # OPTIMIZATION 2: Load existing companies and persons into memory to avoid N+1 queries
            logger.info("Loading existing companies and persons into memory...")
            existing_companies = {c.company_id: c for c in db.query(Company).all()}
            existing_persons = {p.person_id: p for p in db.query(Person).all()}
            logger.info(f"Loaded {len(existing_companies)} existing companies, {len(existing_persons)} existing persons")

            # OPTIMIZATION 3: Disable indexes during import for PostgreSQL performance
            logger.info("Disabling non-essential indexes for faster import...")
            try:
                # Drop indexes that can be recreated (keep primary keys and unique constraints)
                # Table names are singular: company, person
                db.execute(text("DROP INDEX IF EXISTS ix_company_legal_name"))
                db.execute(text("DROP INDEX IF EXISTS ix_company_raw_name"))
                db.execute(text("DROP INDEX IF EXISTS ix_company_register_id"))
                db.execute(text("DROP INDEX IF EXISTS ix_person_last_name"))
                db.execute(text("DROP INDEX IF EXISTS ix_person_first_name"))
                db.commit()
                logger.info("Indexes dropped successfully")
            except Exception as e:
                logger.warning(f"Could not drop indexes: {e}")

            # Prepare batch collections
            companies_to_insert = []
            companies_to_update = []
            persons_to_insert = []
            os_company_batch = []

            # For relationships - store records to process later
            all_records = []

            # Tracking
            processed = 0
            companies_count = 0
            persons_count = 0
            batch_size = 50000

            logger.info("Starting streaming import...")

            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        processed += 1
                        continue

                    try:
                        record = json_loads(line)
                    except (ValueError, TypeError):
                        processed += 1
                        continue

                    company_id = record.get("id", "")

                    # Skip if company already exists
                    if company_id in existing_company_ids:
                        processed += 1
                        continue

                    # Mark as existing to avoid duplicates in this import
                    existing_company_ids.add(company_id)

                    # Extract fields
                    name_obj = record.get("name", {})
                    address_obj = record.get("address", {})
                    register_obj = record.get("register", {})

                    # Extract contact info
                    contact_info = extract_contact_info(record)

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
                    #          last_update_time, full_record, created_at
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

                        # Store relationship data (minimal)
                        roles = rp.get("roles", [])
                        role_type = roles[0].get("type") if roles else rp.get("description")
                        role_desc = rp.get("description")
                        relationships_data.append((company_id, person_id, role_type, role_desc))

                        # Add person if not exists
                        if person_id not in existing_person_ids and person_id not in new_person_ids:
                            new_person_ids.add(person_id)

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
                    if companies_count > 0 and companies_count % batch_size == 0:
                        logger.info(f"Flushing batch at {companies_count} companies...")

                        # COPY companies
                        company_buffer.seek(0)
                        cursor.copy_from(
                            company_buffer,
                            'company',
                            columns=('import_job_id', 'company_id', 'raw_name', 'legal_name', 'legal_form',
                                    'status', 'terminated', 'register_unique_key', 'register_id',
                                    'address_city', 'address_postal_code', 'address_country',
                                    'email', 'website', 'phone', 'domain',
                                    'last_update_time', 'full_record', 'created_at')
                        )

                        # COPY persons
                        person_buffer.seek(0)
                        if person_buffer.tell() > 0 or person_buffer.getvalue():
                            cursor.copy_from(
                                person_buffer,
                                'person',
                                columns=('person_id', 'first_name', 'last_name', 'birth_year',
                                        'address_city', 'full_record', 'created_at')
                            )

                        raw_conn.commit()

                        # Reset buffers
                        company_buffer = io.StringIO()
                        person_buffer = io.StringIO()

                        # Update progress
                        job.processed_lines = processed
                        job.companies_imported = companies_count
                        job.persons_imported = persons_count
                        job.updated_at = datetime.utcnow()
                        db.commit()

                        logger.info(f"Progress: {processed}/{job.total_lines} lines, {companies_count} companies, {persons_count} persons")

            # Final flush
            logger.info("Final flush...")
            company_buffer.seek(0)
            company_data = company_buffer.getvalue()
            if company_data:
                company_buffer = io.StringIO(company_data)
                cursor.copy_from(
                    company_buffer,
                    'company',
                    columns=('import_job_id', 'company_id', 'raw_name', 'legal_name', 'legal_form',
                            'status', 'terminated', 'register_unique_key', 'register_id',
                            'address_city', 'address_postal_code', 'address_country',
                            'email', 'website', 'phone', 'domain',
                            'last_update_time', 'full_record', 'created_at')
                )

            person_buffer.seek(0)
            person_data = person_buffer.getvalue()
            if person_data:
                person_buffer = io.StringIO(person_data)
                cursor.copy_from(
                    person_buffer,
                    'person',
                    columns=('person_id', 'first_name', 'last_name', 'birth_year',
                            'address_city', 'full_record', 'created_at')
                )

            raw_conn.commit()
            logger.info(f"Companies and persons imported: {companies_count} companies, {persons_count} persons")

            # Now create relationships
            logger.info(f"Creating {len(relationships_data)} relationships...")

            # Load ID mappings
            cursor.execute("SELECT id, company_id FROM company")
            company_id_map = {row[1]: row[0] for row in cursor.fetchall()}

            cursor.execute("SELECT id, person_id FROM person")
            person_id_map = {row[1]: row[0] for row in cursor.fetchall()}

            # Load existing relationships
            cursor.execute("SELECT company_db_id, person_db_id, role_type FROM company_person")
            existing_rels = {(row[0], row[1], row[2]) for row in cursor.fetchall()}

            # Build relationship buffer
            rel_buffer = io.StringIO()
            rel_count = 0

            for company_ext_id, person_ext_id, role_type, role_desc in relationships_data:
                company_db_id = company_id_map.get(company_ext_id)
                person_db_id = person_id_map.get(person_ext_id)

                if not company_db_id or not person_db_id:
                    continue

                rel_key = (company_db_id, person_db_id, role_type)
                if rel_key in existing_rels:
                    continue

                existing_rels.add(rel_key)

                rel_line = "\t".join([
                    escape_copy_value(company_db_id),
                    escape_copy_value(person_db_id),
                    escape_copy_value(role_type),
                    escape_copy_value(role_desc),
                    escape_copy_value(None),  # role_date
                ])
                rel_buffer.write(rel_line + "\n")
                rel_count += 1

                # Flush periodically
                if rel_count % 100000 == 0:
                    rel_buffer.seek(0)
                    cursor.copy_from(
                        rel_buffer,
                        'company_person',
                        columns=('company_db_id', 'person_db_id', 'role_type', 'role_description', 'role_date')
                    )
                    raw_conn.commit()
                    rel_buffer = io.StringIO()
                    logger.info(f"Inserted {rel_count} relationships...")

            # Final relationship flush
            rel_buffer.seek(0)
            rel_data = rel_buffer.getvalue()
            if rel_data:
                rel_buffer = io.StringIO(rel_data)
                cursor.copy_from(
                    rel_buffer,
                    'company_person',
                    columns=('company_db_id', 'person_db_id', 'role_type', 'role_description', 'role_date')
                )
            raw_conn.commit()
            logger.info(f"Relationships created: {rel_count}")

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

            # Bulk index to OpenSearch
            if os_client and os_company_batch:
                logger.info(f"Bulk indexing {len(os_company_batch)} companies to OpenSearch...")
                # Index in chunks of 5000
                for i in range(0, len(os_company_batch), 5000):
                    chunk = os_company_batch[i:i+5000]
                    bulk_index(os_client, chunk)
                    logger.info(f"Indexed {min(i+5000, len(os_company_batch))}/{len(os_company_batch)} companies")

            # OPTIMIZATION 8: Index persons to OpenSearch more efficiently
            if os_client:
                logger.info("Indexing persons to OpenSearch...")
                # Build person documents with their roles
                person_docs = []

                # Load all relationships in one query
                all_relationships = db.query(CompanyPerson, Person, Company).join(
                    Person, CompanyPerson.person_db_id == Person.id
                ).join(
                    Company, CompanyPerson.company_db_id == Company.id
                ).all()

                # Group by person
                person_roles = defaultdict(lambda: {"person": None, "company_ids": [], "roles": []})
                for cp, person, company in all_relationships:
                    person_roles[person.person_id]["person"] = person
                    person_roles[person.person_id]["company_ids"].append(company.company_id)
                    person_roles[person.person_id]["roles"].append({
                        "company_id": company.company_id,
                        "company_name": company.legal_name or company.raw_name,
                        "role_type": cp.role_type,
                        "role_date": cp.role_date.isoformat() if cp.role_date else None
                    })

                for person_id, data in person_roles.items():
                    person = data["person"]
                    if not person:
                        continue

                    os_person_doc = {
                        "person_id": person.person_id,
                        "first_name": person.first_name,
                        "last_name": person.last_name,
                        "full_name": f"{person.first_name or ''} {person.last_name or ''}".strip(),
                        "birth_year": person.birth_year,
                        "address_city": person.address_city,
                        "company_ids": data["company_ids"],
                        "roles": data["roles"],
                    }
                    person_docs.append({"_index": PERSON_INDEX, "_id": person.person_id, "_source": os_person_doc})

                # Bulk index persons in chunks
                for i in range(0, len(person_docs), 5000):
                    chunk = person_docs[i:i+5000]
                    bulk_index(os_client, chunk)
                    logger.info(f"Indexed {min(i+5000, len(person_docs))}/{len(person_docs)} persons")

                # Refresh indices to make documents searchable immediately
                os_client.indices.refresh(index=COMPANY_INDEX)
                os_client.indices.refresh(index=PERSON_INDEX)
                logger.info(f"OpenSearch indexing completed: {companies_count} companies, {persons_count} persons")

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
                raw_conn.rollback()
                cursor.close()
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
                   address_country, email, website, domain, last_update_time
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
                        "last_update_time": row[14].isoformat() if row[14] else None,
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
