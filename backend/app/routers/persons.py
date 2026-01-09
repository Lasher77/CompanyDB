import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from typing import Optional
from ..database import get_db
from ..models import Company, Person, CompanyPerson
from ..schemas import (
    PersonListResponse, PersonDetailResponse,
    PersonListItem, PersonCompanyRole
)
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/persons", tags=["persons"])


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


async def search_persons_opensearch(
    client,
    q: Optional[str],
    city: Optional[str],
    limit: int,
    offset: int
) -> tuple[list[dict], int]:
    """Search persons using OpenSearch."""
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
                            "fields": ["first_name^1.5", "last_name^2", "full_name^1.5"],
                            "type": "best_fields",
                            "fuzziness": "AUTO"
                        }
                    },
                    # Exact match on ID
                    {"term": {"person_id": q}}
                ],
                "minimum_should_match": 1
            }
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
            {"last_name.keyword": "asc"},
            {"first_name.keyword": "asc"}
        ]
    }

    response = client.search(index="persons", body=query_body)

    hits = response["hits"]["hits"]
    total = response["hits"]["total"]["value"]

    items = []
    for hit in hits:
        src = hit["_source"]
        items.append({
            "person_id": src.get("person_id"),
            "first_name": src.get("first_name"),
            "last_name": src.get("last_name"),
            "birth_year": src.get("birth_year"),
            "address_city": src.get("address_city"),
        })

    return items, total


async def search_persons_postgres(
    db: AsyncSession,
    q: Optional[str],
    city: Optional[str],
    limit: int,
    offset: int
) -> tuple[list[Person], int]:
    """Search persons using PostgreSQL (fallback)."""
    query = select(Person)

    if q:
        search_term = f"%{q}%"
        query = query.where(
            or_(
                Person.first_name.ilike(search_term),
                Person.last_name.ilike(search_term),
                Person.person_id == q
            )
        )

    if city:
        query = query.where(Person.address_city.ilike(f"%{city}%"))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    query = query.order_by(Person.last_name, Person.first_name).offset(offset).limit(limit)

    result = await db.execute(query)
    persons = result.scalars().all()

    return persons, total


@router.get("", response_model=PersonListResponse)
async def search_persons(
    q: Optional[str] = Query(None, description="Search query for name"),
    city: Optional[str] = Query(None, description="Filter by city"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Search persons with optional filters. Uses OpenSearch if available, PostgreSQL as fallback."""

    # Try OpenSearch first
    os_client = get_opensearch_client()

    if os_client and q:  # Only use OpenSearch for text search
        try:
            items, total = await search_persons_opensearch(
                os_client, q, city, limit, offset
            )
            logger.debug(f"OpenSearch search returned {len(items)} results")

            # Fetch from DB to get complete data including IDs
            person_ids = [item["person_id"] for item in items]
            if person_ids:
                result = await db.execute(
                    select(Person).where(Person.person_id.in_(person_ids))
                )
                persons_map = {p.person_id: p for p in result.scalars().all()}

                # Preserve OpenSearch order and add DB IDs
                final_items = []
                for item in items:
                    if item["person_id"] in persons_map:
                        p = persons_map[item["person_id"]]
                        final_items.append(PersonListItem(
                            id=p.id,
                            person_id=p.person_id,
                            first_name=p.first_name,
                            last_name=p.last_name,
                            birth_year=p.birth_year,
                            address_city=p.address_city,
                        ))

                return PersonListResponse(
                    items=final_items,
                    total=total,
                    limit=limit,
                    offset=offset
                )
        except Exception as e:
            logger.warning(f"OpenSearch search failed, falling back to PostgreSQL: {e}")

    # Fallback to PostgreSQL
    persons, total = await search_persons_postgres(db, q, city, limit, offset)

    return PersonListResponse(
        items=[PersonListItem(
            id=p.id,
            person_id=p.person_id,
            first_name=p.first_name,
            last_name=p.last_name,
            birth_year=p.birth_year,
            address_city=p.address_city,
        ) for p in persons],
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/{person_id}", response_model=PersonDetailResponse)
async def get_person(person_id: str, db: AsyncSession = Depends(get_db)):
    """Get person details by person_id."""
    result = await db.execute(
        select(Person).where(Person.person_id == person_id)
    )
    person = result.scalar_one_or_none()

    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    # Get related companies
    companies_result = await db.execute(
        select(CompanyPerson, Company)
        .join(Company)
        .where(CompanyPerson.person_db_id == person.id)
    )
    related_companies = []
    for cp, company in companies_result:
        related_companies.append(PersonCompanyRole(
            company_id=company.company_id,
            legal_name=company.legal_name,
            raw_name=company.raw_name,
            status=company.status,
            role_type=cp.role_type,
            role_description=cp.role_description,
            role_date=cp.role_date
        ))

    return PersonDetailResponse(
        id=person.id,
        person_id=person.person_id,
        first_name=person.first_name,
        last_name=person.last_name,
        birth_year=person.birth_year,
        address_city=person.address_city,
        full_record=person.full_record,
        related_companies=related_companies,
        created_at=person.created_at
    )
