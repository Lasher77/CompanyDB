from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from typing import Optional
from ..database import get_db
from ..models import Company, Person, CompanyPerson
from ..schemas import (
    PersonListResponse, PersonDetailResponse,
    PersonCompanyRole
)

router = APIRouter(prefix="/persons", tags=["persons"])


@router.get("", response_model=PersonListResponse)
async def search_persons(
    q: Optional[str] = Query(None, description="Search query for name"),
    city: Optional[str] = Query(None, description="Filter by city"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Search persons with optional filters."""
    query = select(Person)

    # Apply filters
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

    return PersonListResponse(
        items=[{
            "id": p.id,
            "person_id": p.person_id,
            "first_name": p.first_name,
            "last_name": p.last_name,
            "birth_year": p.birth_year,
            "address_city": p.address_city,
        } for p in persons],
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
