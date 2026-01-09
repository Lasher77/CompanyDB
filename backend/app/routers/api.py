"""
External API for Salesforce and other integrations.
Provides company matching/lookup with scoring.
"""
import logging
import re
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from pydantic import BaseModel, Field
from ..database import get_db
from ..models import Company
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["api"])


# Request/Response Models
class MatchQuery(BaseModel):
    name: Optional[str] = Field(None, description="Company name")
    city: Optional[str] = Field(None, description="City")
    postal_code: Optional[str] = Field(None, description="Postal code")
    street: Optional[str] = Field(None, description="Street address")
    domain: Optional[str] = Field(None, description="Website domain")
    email: Optional[str] = Field(None, description="Email address")


class MatchOptions(BaseModel):
    min_score: float = Field(0.5, ge=0.0, le=1.0, description="Minimum match score (0-1)")
    max_results: int = Field(10, ge=1, le=100, description="Maximum number of results")


class MatchRequest(BaseModel):
    query: MatchQuery
    options: Optional[MatchOptions] = None


class MatchedCompany(BaseModel):
    company_id: str
    name: str
    legal_form: Optional[str]
    status: Optional[str]
    address_city: Optional[str]
    address_postal_code: Optional[str]
    address_country: Optional[str]
    register_id: Optional[str]
    register_unique_key: Optional[str]
    score: float
    match_details: dict


class MatchResponse(BaseModel):
    success: bool
    count: int
    results: List[MatchedCompany]


# Authentication dependency
async def verify_api_key(authorization: Optional[str] = Header(None)):
    """Verify Bearer token authentication."""
    if not settings.api_keys:
        # No API keys configured = no auth required (development mode)
        logger.warning("No API keys configured - running without authentication")
        return True

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header format. Use 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = authorization[7:]  # Remove "Bearer " prefix

    if token not in settings.api_keys:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return True


# Matching helper functions
def normalize_string(s: Optional[str]) -> str:
    """Normalize string for comparison."""
    if not s:
        return ""
    # Lowercase, remove extra whitespace
    s = " ".join(s.lower().split())
    # Remove common legal form suffixes for comparison
    s = re.sub(r'\s+(gmbh|ag|kg|ohg|gbr|ug|e\.?k\.?|mbh|co\.?\s*kg|gmbh\s*&\s*co\.?\s*kg)\.?\s*$', '', s, flags=re.IGNORECASE)
    return s.strip()


def extract_domain(url_or_email: Optional[str]) -> str:
    """Extract domain from URL or email."""
    if not url_or_email:
        return ""
    # Remove protocol
    domain = re.sub(r'^https?://', '', url_or_email.lower())
    # Remove www.
    domain = re.sub(r'^www\.', '', domain)
    # Get domain from email
    if '@' in domain:
        domain = domain.split('@')[1]
    # Remove path
    domain = domain.split('/')[0]
    return domain.strip()


def calculate_similarity(s1: str, s2: str) -> float:
    """Calculate similarity between two strings (0-1)."""
    if not s1 or not s2:
        return 0.0
    s1, s2 = s1.lower(), s2.lower()
    if s1 == s2:
        return 1.0

    # Check if one contains the other
    if s1 in s2 or s2 in s1:
        return 0.8

    # Simple word overlap score
    words1 = set(s1.split())
    words2 = set(s2.split())
    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union) if union else 0.0


def score_company(company: Company, query: MatchQuery) -> tuple[float, dict]:
    """Calculate match score for a company against the query."""
    scores = {}
    weights = {
        'name': 0.4,
        'city': 0.15,
        'postal_code': 0.15,
        'domain': 0.2,
        'street': 0.1,
    }

    # Name matching
    if query.name:
        query_name = normalize_string(query.name)
        company_name = normalize_string(company.legal_name or company.raw_name)
        name_score = calculate_similarity(query_name, company_name)
        scores['name'] = name_score

    # City matching
    if query.city and company.address_city:
        city_score = 1.0 if query.city.lower() == company.address_city.lower() else 0.0
        if city_score == 0 and (query.city.lower() in company.address_city.lower() or
                                 company.address_city.lower() in query.city.lower()):
            city_score = 0.7
        scores['city'] = city_score

    # Postal code matching
    if query.postal_code and company.address_postal_code:
        if query.postal_code == company.address_postal_code:
            scores['postal_code'] = 1.0
        elif query.postal_code[:3] == company.address_postal_code[:3]:
            scores['postal_code'] = 0.5
        else:
            scores['postal_code'] = 0.0

    # Domain matching (from full_record)
    if query.domain or query.email:
        query_domain = extract_domain(query.domain) or extract_domain(query.email)
        if query_domain and company.full_record:
            company_domain = ""
            # Try to extract domain from company data
            if company.full_record.get("website"):
                company_domain = extract_domain(company.full_record.get("website"))
            elif company.full_record.get("domain"):
                company_domain = extract_domain(company.full_record.get("domain"))

            if company_domain and query_domain:
                scores['domain'] = 1.0 if query_domain == company_domain else 0.0

    # Calculate weighted total score
    total_weight = 0.0
    total_score = 0.0

    for field, score in scores.items():
        weight = weights.get(field, 0.1)
        total_score += score * weight
        total_weight += weight

    # Normalize score
    final_score = total_score / total_weight if total_weight > 0 else 0.0

    return final_score, scores


@router.post("/match", response_model=MatchResponse)
async def match_companies(
    request: MatchRequest,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key)
):
    """
    Find matching companies based on provided criteria.

    Returns companies sorted by match score with detailed scoring breakdown.
    """
    query = request.query
    options = request.options or MatchOptions()

    # Build database query
    db_query = select(Company)
    conditions = []

    # Name search (required for meaningful results)
    if query.name:
        search_term = f"%{query.name}%"
        conditions.append(
            or_(
                Company.raw_name.ilike(search_term),
                Company.legal_name.ilike(search_term)
            )
        )

    # City filter
    if query.city:
        conditions.append(Company.address_city.ilike(f"%{query.city}%"))

    # Postal code filter
    if query.postal_code:
        conditions.append(Company.address_postal_code.ilike(f"{query.postal_code}%"))

    if not conditions:
        raise HTTPException(
            status_code=400,
            detail="At least one search criterion (name, city, or postal_code) is required"
        )

    db_query = db_query.where(or_(*conditions))
    db_query = db_query.limit(100)  # Fetch more to filter by score later

    result = await db.execute(db_query)
    companies = result.scalars().all()

    # Score and rank results
    scored_results = []
    for company in companies:
        score, match_details = score_company(company, query)
        if score >= options.min_score:
            scored_results.append(MatchedCompany(
                company_id=company.company_id,
                name=company.legal_name or company.raw_name or "",
                legal_form=company.legal_form,
                status=company.status,
                address_city=company.address_city,
                address_postal_code=company.address_postal_code,
                address_country=company.address_country,
                register_id=company.register_id,
                register_unique_key=company.register_unique_key,
                score=round(score, 3),
                match_details=match_details
            ))

    # Sort by score descending
    scored_results.sort(key=lambda x: x.score, reverse=True)

    # Limit results
    scored_results = scored_results[:options.max_results]

    return MatchResponse(
        success=True,
        count=len(scored_results),
        results=scored_results
    )


@router.get("/company/{company_id}")
async def get_company_by_id(
    company_id: str,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key)
):
    """Get company details by company_id."""
    result = await db.execute(
        select(Company).where(Company.company_id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    return {
        "success": True,
        "company": {
            "company_id": company.company_id,
            "name": company.legal_name or company.raw_name,
            "raw_name": company.raw_name,
            "legal_form": company.legal_form,
            "status": company.status,
            "terminated": company.terminated,
            "address": {
                "city": company.address_city,
                "postal_code": company.address_postal_code,
                "country": company.address_country
            },
            "register": {
                "id": company.register_id,
                "unique_key": company.register_unique_key
            },
            "last_update_time": company.last_update_time.isoformat() if company.last_update_time else None,
            "full_record": company.full_record
        }
    }
