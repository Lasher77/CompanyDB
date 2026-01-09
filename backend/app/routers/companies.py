from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from typing import Optional
from ..database import get_db
from ..models import Company, Person, CompanyPerson
from ..schemas import (
    CompanyListResponse, CompanyDetailResponse,
    PersonListResponse, PersonDetailResponse,
    CompanyPersonRole
)

router = APIRouter(prefix="/companies", tags=["companies"])


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
    """Search companies with optional filters."""
    query = select(Company)

    # Apply filters
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

    return CompanyListResponse(
        items=[{
            "id": c.id,
            "company_id": c.company_id,
            "raw_name": c.raw_name,
            "legal_name": c.legal_name,
            "legal_form": c.legal_form,
            "status": c.status,
            "terminated": c.terminated,
            "address_city": c.address_city,
            "address_country": c.address_country,
            "register_id": c.register_id,
        } for c in companies],
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
