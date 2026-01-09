import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from typing import Optional
from ..database import get_db
from ..models import Company, Person, CompanyPerson
from ..schemas import (
    CompanyListResponse, CompanyDetailResponse,
    CompanyListItem, CompanyPersonRole
)
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["companies"])


def get_opensearch_client():
    """Get OpenSearch client if available."""
    if not settings.opensearch_enabled:
        return None
    try:
        from ..opensearch_client import get_opensearch_client as get_os_client
        client = get_os_client()
        # Quick health check
        client.cluster.health(timeout="2s")
        return client
    except Exception as e:
        logger.warning(f"OpenSearch not available: {e}")
        return None


async def search_companies_opensearch(
    client,
    q: Optional[str],
    status: Optional[str],
    legal_form: Optional[str],
    city: Optional[str],
    limit: int,
    offset: int
) -> tuple[list[dict], int]:
    """Search companies using OpenSearch."""
    must_clauses = []
    filter_clauses = []

    if q:
        # Multi-match with fuzzy for name search
        must_clauses.append({
            "bool": {
                "should": [
                    {
                        "multi_match": {
                            "query": q,
                            "fields": ["raw_name^2", "legal_name^2", "register_id"],
                            "type": "best_fields",
                            "fuzziness": "AUTO"
                        }
                    },
                    # Exact match on IDs
                    {"term": {"company_id": q}},
                    {"term": {"register_unique_key": q}}
                ],
                "minimum_should_match": 1
            }
        })

    if status:
        filter_clauses.append({"term": {"status": status}})

    if legal_form:
        filter_clauses.append({
            "wildcard": {"legal_form": f"*{legal_form.lower()}*"}
        })

    if city:
        filter_clauses.append({
            "wildcard": {"address_city": f"*{city}*"}
        })

    query_body = {
        "query": {
            "bool": {
                "must": must_clauses if must_clauses else [{"match_all": {}}],
                "filter": filter_clauses
            }
        },
        "from": offset,
        "size": limit,
        "sort": [
            {"_score": "desc"},
            {"legal_name.keyword": "asc"}
        ]
    }

    response = client.search(index="companies", body=query_body)

    hits = response["hits"]["hits"]
    total = response["hits"]["total"]["value"]

    items = []
    for hit in hits:
        src = hit["_source"]
        items.append({
            "company_id": src.get("company_id"),
            "raw_name": src.get("raw_name"),
            "legal_name": src.get("legal_name"),
            "legal_form": src.get("legal_form"),
            "status": src.get("status"),
            "terminated": src.get("terminated"),
            "address_city": src.get("address_city"),
            "address_country": src.get("address_country"),
            "register_id": src.get("register_id"),
        })

    return items, total


async def search_companies_postgres(
    db: AsyncSession,
    q: Optional[str],
    status: Optional[str],
    legal_form: Optional[str],
    city: Optional[str],
    limit: int,
    offset: int
) -> tuple[list[Company], int]:
    """Search companies using PostgreSQL (fallback)."""
    query = select(Company)

    if q:
        search_term = f"%{q}%"
        query = query.where(
            or_(
                Company.raw_name.ilike(search_term),
                Company.legal_name.ilike(search_term),
                Company.company_id == q,
                Company.register_unique_key == q,
                Company.register_id.ilike(search_term)
            )
        )

    if status:
        query = query.where(Company.status == status)

    if legal_form:
        query = query.where(Company.legal_form.ilike(f"%{legal_form}%"))

    if city:
        query = query.where(Company.address_city.ilike(f"%{city}%"))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    query = query.order_by(Company.legal_name).offset(offset).limit(limit)

    result = await db.execute(query)
    companies = result.scalars().all()

    return companies, total


@router.get("", response_model=CompanyListResponse)
async def search_companies(
    q: Optional[str] = Query(None, description="Search query for name"),
    status: Optional[str] = Query(None, description="Filter by status (active/terminated/liquidation)"),
    legal_form: Optional[str] = Query(None, description="Filter by legal form"),
    city: Optional[str] = Query(None, description="Filter by city"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Search companies with optional filters. Uses OpenSearch if available, PostgreSQL as fallback."""

    # Try OpenSearch first
    os_client = get_opensearch_client()

    if os_client and q:  # Only use OpenSearch for text search
        try:
            items, total = await search_companies_opensearch(
                os_client, q, status, legal_form, city, limit, offset
            )
            logger.debug(f"OpenSearch search returned {len(items)} results")

            # We need to get the DB IDs for the items
            # Fetch from DB to get complete data including IDs
            company_ids = [item["company_id"] for item in items]
            if company_ids:
                result = await db.execute(
                    select(Company).where(Company.company_id.in_(company_ids))
                )
                companies_map = {c.company_id: c for c in result.scalars().all()}

                # Preserve OpenSearch order and add DB IDs
                final_items = []
                for item in items:
                    if item["company_id"] in companies_map:
                        c = companies_map[item["company_id"]]
                        final_items.append(CompanyListItem(
                            id=c.id,
                            company_id=c.company_id,
                            raw_name=c.raw_name,
                            legal_name=c.legal_name,
                            legal_form=c.legal_form,
                            status=c.status,
                            terminated=c.terminated,
                            address_city=c.address_city,
                            address_country=c.address_country,
                            register_id=c.register_id,
                        ))

                return CompanyListResponse(
                    items=final_items,
                    total=total,
                    limit=limit,
                    offset=offset
                )
        except Exception as e:
            logger.warning(f"OpenSearch search failed, falling back to PostgreSQL: {e}")

    # Fallback to PostgreSQL
    companies, total = await search_companies_postgres(
        db, q, status, legal_form, city, limit, offset
    )

    return CompanyListResponse(
        items=[CompanyListItem(
            id=c.id,
            company_id=c.company_id,
            raw_name=c.raw_name,
            legal_name=c.legal_name,
            legal_form=c.legal_form,
            status=c.status,
            terminated=c.terminated,
            address_city=c.address_city,
            address_country=c.address_country,
            register_id=c.register_id,
        ) for c in companies],
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/{company_id}", response_model=CompanyDetailResponse)
async def get_company(company_id: str, db: AsyncSession = Depends(get_db)):
    """Get company details by company_id."""
    result = await db.execute(
        select(Company).where(Company.company_id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Get related persons
    persons_result = await db.execute(
        select(CompanyPerson, Person)
        .join(Person)
        .where(CompanyPerson.company_db_id == company.id)
    )
    related_persons = []
    for cp, person in persons_result:
        related_persons.append(CompanyPersonRole(
            person_id=person.person_id,
            first_name=person.first_name,
            last_name=person.last_name,
            role_type=cp.role_type,
            role_description=cp.role_description,
            role_date=cp.role_date
        ))

    return CompanyDetailResponse(
        id=company.id,
        company_id=company.company_id,
        raw_name=company.raw_name,
        legal_name=company.legal_name,
        legal_form=company.legal_form,
        status=company.status,
        terminated=company.terminated,
        register_unique_key=company.register_unique_key,
        register_id=company.register_id,
        address_city=company.address_city,
        address_postal_code=company.address_postal_code,
        address_country=company.address_country,
        last_update_time=company.last_update_time,
        full_record=company.full_record,
        related_persons=related_persons,
        created_at=company.created_at
    )
