import csv
import io
import logging
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_db
from ..models import Company, Person, CompanyPerson
from ..schemas import ExportRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["export"])

MAX_EXPORT_LIMIT = 1000


def extract_fax_from_record(full_record: dict) -> str | None:
    """Extract fax number from the extras array in full_record."""
    extras = full_record.get("extras", [])
    for source in extras:
        items = source.get("items", [])
        for item in items:
            if item.get("id") == "fax":
                return item.get("value")
    return None


def extract_founding_year_from_record(full_record: dict) -> int | None:
    """Extract founding year from events (type 'NewCompany')."""
    events = full_record.get("events", {}).get("items", [])
    for event in events:
        if event.get("type") == "NewCompany":
            date_str = event.get("date")
            if date_str:
                try:
                    return int(date_str[:4])
                except (ValueError, TypeError):
                    pass
    return None


def extract_address_street_from_record(full_record: dict) -> str | None:
    """Extract street address from full_record."""
    address = full_record.get("address", {})
    return address.get("street") or None


def extract_wz_code_from_record(full_record: dict) -> str:
    """Extract WZ code (Wirtschaftszweig) from segmentCodes.

    Tries wz2025 first, then wz. Returns code and description combined.
    """
    segment_codes = full_record.get("segmentCodes", {})

    # Try wz2025 first (newer classification)
    wz_codes = segment_codes.get("wz2025", []) or segment_codes.get("wz", [])

    if not wz_codes:
        return ""

    # Return first WZ code with description
    first_code = wz_codes[0] if wz_codes else {}
    code = first_code.get("code", "")
    description = first_code.get("description", "")

    if code and description:
        return f"{code} - {description}"
    return code or description or ""


def format_currency(value: float | None) -> str:
    """Format currency value for CSV."""
    if value is None:
        return ""
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@router.post("/companies")
async def export_companies(
    request: ExportRequest,
    db: AsyncSession = Depends(get_db)
):
    """Export selected companies as CSV.

    Returns a CSV file with company data including:
    - Address (street, postal code, city, country)
    - Contact info (email, website, phone, fax)
    - Founding year
    - Employee count
    - Revenue
    """
    if len(request.company_ids) > MAX_EXPORT_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_EXPORT_LIMIT} companies can be exported at once"
        )

    if not request.company_ids:
        raise HTTPException(status_code=400, detail="No companies selected")

    # Fetch companies by their company_id
    result = await db.execute(
        select(Company).where(Company.company_id.in_(request.company_ids))
    )
    companies = result.scalars().all()

    if not companies:
        raise HTTPException(status_code=404, detail="No companies found")

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_ALL)

    # Write header
    writer.writerow([
        "Company ID",
        "Name",
        "Legal Form",
        "Status",
        "Street",
        "Postal Code",
        "City",
        "Country",
        "Email",
        "Website",
        "Phone",
        "Fax",
        "Founding Year",
        "Employee Count",
        "Revenue (EUR)",
        "WZ Code",
        "Register ID"
    ])

    # Write data
    for company in companies:
        full_record = company.full_record or {}

        writer.writerow([
            company.company_id,
            company.legal_name or company.raw_name or "",
            company.legal_form or "",
            company.status or "",
            extract_address_street_from_record(full_record) or "",
            company.address_postal_code or "",
            company.address_city or "",
            company.address_country or "",
            company.email or "",
            company.website or "",
            company.phone or "",
            extract_fax_from_record(full_record) or "",
            extract_founding_year_from_record(full_record) or "",
            company.employee_count if company.employee_count is not None else "",
            format_currency(company.last_revenue),
            extract_wz_code_from_record(full_record),
            company.register_id or ""
        ])

    # Prepare response
    output.seek(0)

    # Add BOM for Excel compatibility
    content = '\ufeff' + output.getvalue()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"companies_export_{timestamp}.csv"

    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.post("/persons")
async def export_persons(
    request: ExportRequest,
    db: AsyncSession = Depends(get_db)
):
    """Export persons related to selected companies as CSV.

    Returns a CSV with:
    - Person data (name, birth date, city)
    - Role information (type, description)
    - Reference to the company
    """
    if len(request.company_ids) > MAX_EXPORT_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_EXPORT_LIMIT} companies can be exported at once"
        )

    if not request.company_ids:
        raise HTTPException(status_code=400, detail="No companies selected")

    # Fetch companies first to get their DB IDs
    company_result = await db.execute(
        select(Company).where(Company.company_id.in_(request.company_ids))
    )
    companies = {c.id: c for c in company_result.scalars().all()}

    if not companies:
        raise HTTPException(status_code=404, detail="No companies found")

    # Fetch all person relationships for these companies
    persons_result = await db.execute(
        select(CompanyPerson, Person)
        .join(Person)
        .where(CompanyPerson.company_db_id.in_(companies.keys()))
    )

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_ALL)

    # Write header
    writer.writerow([
        "Company ID",
        "Company Name",
        "Person ID",
        "First Name",
        "Last Name",
        "Birth Date",
        "City",
        "Role Type",
        "Role Description",
        "Role Date"
    ])

    # Write data - all persons
    for cp, person in persons_result:
        company = companies.get(cp.company_db_id)
        if not company:
            continue

        # Extract full birth date from person's full_record
        full_record = person.full_record or {}
        birth_date = full_record.get("birthDate", "")

        writer.writerow([
            company.company_id,
            company.legal_name or company.raw_name or "",
            person.person_id,
            person.first_name or "",
            person.last_name or "",
            birth_date,
            person.address_city or "",
            cp.role_type or "",
            cp.role_description or "",
            cp.role_date.isoformat() if cp.role_date else ""
        ])

    # Prepare response
    output.seek(0)

    # Add BOM for Excel compatibility
    content = '\ufeff' + output.getvalue()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"persons_export_{timestamp}.csv"

    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
