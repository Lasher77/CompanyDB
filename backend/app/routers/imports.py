import json
import threading
import logging
from datetime import datetime
from uuid import UUID
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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
    thread = threading.Thread(target=run_import_job, args=(import_job.id, file_path))
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


def run_import_job(job_id: UUID, file_path: Path):
    """Run the import job in a background thread (sync)."""
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=sync_engine)

    with SessionLocal() as db:
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if not job:
            return

        job.status = "running"
        job.updated_at = datetime.utcnow()
        db.commit()

        # OpenSearch client (optional)
        os_client = None
        COMPANY_INDEX = "companies"
        PERSON_INDEX = "persons"

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

            batch_size = settings.import_batch_size
            os_company_batch = []
            persons_cache = {}  # person_id -> Person record

            processed = 0
            companies_count = 0
            persons_count = 0

            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        processed += 1
                        continue

                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        processed += 1
                        continue

                    # Extract company fields
                    company_id = record.get("id", "")
                    name_obj = record.get("name", {})
                    address_obj = record.get("address", {})
                    register_obj = record.get("register", {})
                    segment_codes = record.get("segmentCodes", {})

                    # Check if company already exists
                    existing = db.query(Company).filter(Company.company_id == company_id).first()
                    if existing:
                        # Update existing
                        existing.raw_name = record.get("rawName")
                        existing.legal_name = name_obj.get("name")
                        existing.legal_form = name_obj.get("legalForm")
                        existing.status = record.get("status")
                        existing.terminated = record.get("terminated")
                        existing.register_unique_key = register_obj.get("uniqueKey")
                        existing.register_id = register_obj.get("id")
                        existing.address_city = address_obj.get("city")
                        existing.address_postal_code = address_obj.get("postalCode")
                        existing.address_country = address_obj.get("country")
                        existing.full_record = record
                        if record.get("lastUpdateTime"):
                            try:
                                existing.last_update_time = datetime.fromisoformat(record["lastUpdateTime"].replace("Z", "+00:00"))
                            except:
                                pass
                        existing.import_job_id = job_id
                    else:
                        # Create new company
                        company_db = Company(
                            import_job_id=job_id,
                            company_id=company_id,
                            raw_name=record.get("rawName"),
                            legal_name=name_obj.get("name"),
                            legal_form=name_obj.get("legalForm"),
                            status=record.get("status"),
                            terminated=record.get("terminated"),
                            register_unique_key=register_obj.get("uniqueKey"),
                            register_id=register_obj.get("id"),
                            address_city=address_obj.get("city"),
                            address_postal_code=address_obj.get("postalCode"),
                            address_country=address_obj.get("country"),
                            full_record=record,
                        )
                        if record.get("lastUpdateTime"):
                            try:
                                company_db.last_update_time = datetime.fromisoformat(record["lastUpdateTime"].replace("Z", "+00:00"))
                            except:
                                pass
                        db.add(company_db)
                        companies_count += 1

                    # Prepare OpenSearch document for company (only if OpenSearch available)
                    if os_client:
                        os_company_doc = {
                            "company_id": company_id,
                            "raw_name": record.get("rawName"),
                            "legal_name": name_obj.get("name"),
                            "legal_form": name_obj.get("legalForm"),
                            "status": record.get("status"),
                            "terminated": record.get("terminated"),
                            "register_unique_key": register_obj.get("uniqueKey"),
                            "register_id": register_obj.get("id"),
                            "address_city": address_obj.get("city"),
                            "address_postal_code": address_obj.get("postalCode"),
                            "address_country": address_obj.get("country"),
                            "segment_codes_wz": segment_codes.get("wz", []),
                            "segment_codes_nace": segment_codes.get("nace", []),
                            "last_update_time": record.get("lastUpdateTime"),
                        }
                        os_company_batch.append({"_index": COMPANY_INDEX, "_id": company_id, "_source": os_company_doc})

                    # Process related persons
                    related_persons = record.get("relatedPersons", {}).get("items", [])
                    for rp in related_persons:
                        person_data = rp.get("person", {})
                        person_id = person_data.get("id")
                        if not person_id:
                            continue

                        person_name = person_data.get("name", {})
                        person_address = person_data.get("address", {})

                        # Check if person already processed in this batch
                        if person_id not in persons_cache:
                            # Check if person exists in DB
                            existing_person = db.query(Person).filter(Person.person_id == person_id).first()
                            if existing_person:
                                persons_cache[person_id] = existing_person
                            else:
                                new_person = Person(
                                    person_id=person_id,
                                    first_name=person_name.get("firstName"),
                                    last_name=person_name.get("lastName"),
                                    birth_year=person_data.get("birthYear"),
                                    address_city=person_address.get("city"),
                                    full_record=person_data,
                                )
                                db.add(new_person)
                                persons_cache[person_id] = new_person
                                persons_count += 1

                    processed += 1

                    # Commit batch
                    if processed % batch_size == 0:
                        db.commit()

                        # Bulk index to OpenSearch
                        if os_client and os_company_batch:
                            bulk_index(os_client, os_company_batch)
                            os_company_batch = []

                        # Update progress
                        job.processed_lines = processed
                        job.companies_imported = companies_count
                        job.persons_imported = persons_count
                        job.updated_at = datetime.utcnow()
                        db.commit()

            # Process remaining batch
            db.commit()
            if os_client and os_company_batch:
                bulk_index(os_client, os_company_batch)

            # Now create company_person relationships
            # We need to do this after companies are committed to get their IDs
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except:
                        continue

                    company_id = record.get("id")
                    company_db = db.query(Company).filter(Company.company_id == company_id).first()
                    if not company_db:
                        continue

                    related_persons = record.get("relatedPersons", {}).get("items", [])
                    for rp in related_persons:
                        person_data = rp.get("person", {})
                        person_id = person_data.get("id")
                        if not person_id:
                            continue

                        person_db = db.query(Person).filter(Person.person_id == person_id).first()
                        if not person_db:
                            continue

                        # Get role info
                        roles = rp.get("roles", [])
                        role_type = roles[0].get("type") if roles else rp.get("description")
                        role_desc = rp.get("description")
                        role_date = None
                        if roles and roles[0].get("date"):
                            try:
                                role_date = datetime.strptime(roles[0]["date"], "%Y-%m-%d").date()
                            except:
                                pass

                        # Check if relationship exists
                        existing_rel = db.query(CompanyPerson).filter(
                            CompanyPerson.company_db_id == company_db.id,
                            CompanyPerson.person_db_id == person_db.id,
                            CompanyPerson.role_type == role_type
                        ).first()

                        if not existing_rel:
                            rel = CompanyPerson(
                                company_db_id=company_db.id,
                                person_db_id=person_db.id,
                                role_type=role_type,
                                role_description=role_desc,
                                role_date=role_date,
                            )
                            db.add(rel)

            db.commit()

            # Index persons to OpenSearch (only if available)
            if os_client:
                logger.info("Indexing persons to OpenSearch...")
                persons = db.query(Person).all()
                os_person_batch = []
                for person in persons:
                    # Get all companies for this person
                    company_roles = db.query(CompanyPerson, Company).join(Company).filter(
                        CompanyPerson.person_db_id == person.id
                    ).all()

                    roles_list = []
                    company_ids = []
                    for cp, company in company_roles:
                        company_ids.append(company.company_id)
                        roles_list.append({
                            "company_id": company.company_id,
                            "company_name": company.legal_name or company.raw_name,
                            "role_type": cp.role_type,
                            "role_date": cp.role_date.isoformat() if cp.role_date else None
                        })

                    os_person_doc = {
                        "person_id": person.person_id,
                        "first_name": person.first_name,
                        "last_name": person.last_name,
                        "full_name": f"{person.first_name or ''} {person.last_name or ''}".strip(),
                        "birth_year": person.birth_year,
                        "address_city": person.address_city,
                        "company_ids": company_ids,
                        "roles": roles_list,
                    }
                    os_person_batch.append({"_index": PERSON_INDEX, "_id": person.person_id, "_source": os_person_doc})

                    # Bulk index every 1000 persons
                    if len(os_person_batch) >= 1000:
                        bulk_index(os_client, os_person_batch)
                        os_person_batch = []

                if os_person_batch:
                    bulk_index(os_client, os_person_batch)

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

        except Exception as e:
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
    thread = threading.Thread(target=run_reindex)
    thread.start()

    return {"status": "started", "message": "Reindexing started in background"}


def run_reindex():
    """Run the reindex job in a background thread (sync)."""
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=sync_engine)

    COMPANY_INDEX = "companies"
    PERSON_INDEX = "persons"

    try:
        from ..opensearch_client import get_opensearch_client, init_opensearch_indices
        os_client = get_opensearch_client()

        # Create indices if they don't exist
        init_opensearch_indices(os_client)
        logger.info("OpenSearch indices initialized")

        with SessionLocal() as db:
            # Index all companies
            companies = db.query(Company).all()
            logger.info(f"Indexing {len(companies)} companies to OpenSearch")

            os_company_batch = []
            for company in companies:
                full_record = company.full_record or {}
                segment_codes = full_record.get("segmentCodes", {})

                os_company_doc = {
                    "company_id": company.company_id,
                    "raw_name": company.raw_name,
                    "legal_name": company.legal_name,
                    "legal_form": company.legal_form,
                    "status": company.status,
                    "terminated": company.terminated,
                    "register_unique_key": company.register_unique_key,
                    "register_id": company.register_id,
                    "address_city": company.address_city,
                    "address_postal_code": company.address_postal_code,
                    "address_country": company.address_country,
                    "segment_codes_wz": segment_codes.get("wz", []),
                    "segment_codes_nace": segment_codes.get("nace", []),
                    "last_update_time": company.last_update_time.isoformat() if company.last_update_time else None,
                }
                os_company_batch.append({"_index": COMPANY_INDEX, "_id": company.company_id, "_source": os_company_doc})

                # Bulk index every 1000 documents
                if len(os_company_batch) >= 1000:
                    bulk_index(os_client, os_company_batch)
                    os_company_batch = []

            # Index remaining companies
            if os_company_batch:
                bulk_index(os_client, os_company_batch)

            logger.info(f"Companies indexed successfully")

            # Index all persons
            persons = db.query(Person).all()
            logger.info(f"Indexing {len(persons)} persons to OpenSearch")

            os_person_batch = []
            for person in persons:
                # Get all companies for this person
                company_roles = db.query(CompanyPerson, Company).join(Company).filter(
                    CompanyPerson.person_db_id == person.id
                ).all()

                roles_list = []
                company_ids = []
                for cp, company in company_roles:
                    company_ids.append(company.company_id)
                    roles_list.append({
                        "company_id": company.company_id,
                        "company_name": company.legal_name or company.raw_name,
                        "role_type": cp.role_type,
                        "role_date": cp.role_date.isoformat() if cp.role_date else None
                    })

                os_person_doc = {
                    "person_id": person.person_id,
                    "first_name": person.first_name,
                    "last_name": person.last_name,
                    "full_name": f"{person.first_name or ''} {person.last_name or ''}".strip(),
                    "birth_year": person.birth_year,
                    "address_city": person.address_city,
                    "company_ids": company_ids,
                    "roles": roles_list,
                }
                os_person_batch.append({"_index": PERSON_INDEX, "_id": person.person_id, "_source": os_person_doc})

                # Bulk index every 1000 documents
                if len(os_person_batch) >= 1000:
                    bulk_index(os_client, os_person_batch)
                    os_person_batch = []

            # Index remaining persons
            if os_person_batch:
                bulk_index(os_client, os_person_batch)

            logger.info(f"Persons indexed successfully")

            # Refresh indices to make documents searchable immediately
            os_client.indices.refresh(index=COMPANY_INDEX)
            os_client.indices.refresh(index=PERSON_INDEX)

            logger.info("Reindex completed successfully")

    except Exception as e:
        logger.error(f"Reindex failed: {e}")
        raise
