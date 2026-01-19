"""
External API for Salesforce and other integrations.
Provides company matching/lookup with scoring.

Matching Strategy:
- Multi-stage fallback search for better recall
- Legal form normalization (GmbH, gGmbH, AG, etc.)
- Word-based name matching
- Domain as fallback when name matching fails
"""
import logging
import re
from typing import Optional, List, Set
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func
from pydantic import BaseModel, Field
from ..database import get_db
from ..models import Company
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["api"])

# Legal form patterns for normalization
LEGAL_FORM_PATTERNS = [
    # Full forms first (longer patterns)
    (r'gemeinn[üu]tzige\s+gesellschaft\s+mit\s+beschr[äa]nkter\s+haftung', ''),
    (r'gesellschaft\s+mit\s+beschr[äa]nkter\s+haftung', ''),
    (r'gesellschaft\s+b[üu]rgerlichen\s+rechts', ''),
    (r'offene\s+handelsgesellschaft', ''),
    (r'kommanditgesellschaft\s+auf\s+aktien', ''),
    (r'aktiengesellschaft', ''),
    (r'kommanditgesellschaft', ''),
    (r'eingetragener\s+kaufmann', ''),
    (r'eingetragene\s+kauffrau', ''),
    # Abbreviations with variations
    (r'ggmbh', ''),
    (r'gmbh\s*&\s*co\.?\s*kg', ''),
    (r'gmbh\s*&\s*co\.?\s*ohg', ''),
    (r'ag\s*&\s*co\.?\s*kg', ''),
    (r'gmbh', ''),
    (r'mbh', ''),
    (r'ohg', ''),
    (r'gbr', ''),
    (r'kgaa', ''),
    (r'u\.?g\.?\s*\(haftungsbeschr[äa]nkt\)', ''),
    (r'ug', ''),
    (r'e\.?\s*k\.?', ''),
    (r'ag', ''),
    (r'kg', ''),
    (r'se', ''),  # Societas Europaea
    (r'e\.?\s*v\.?', ''),  # eingetragener Verein
    (r'ltd\.?', ''),
    (r'inc\.?', ''),
    (r'corp\.?', ''),
    (r'plc', ''),
    (r's\.?a\.?r\.?l\.?', ''),
    (r'b\.?v\.?', ''),
    (r's\.?a\.?', ''),
    (r's\.?r\.?l\.?', ''),
]


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
    email: Optional[str]
    website: Optional[str]
    domain: Optional[str]
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
def normalize_company_name(s: Optional[str]) -> str:
    """
    Normalize company name by removing legal forms and standardizing format.

    Examples:
    - "RAL gGmbH" -> "ral"
    - "RAL gemeinnützige GmbH" -> "ral"
    - "Wacker Burghausen Fußball GmbH" -> "wacker burghausen fußball"
    """
    if not s:
        return ""
    # Lowercase and normalize whitespace
    s = " ".join(s.lower().split())

    # Remove all legal form patterns
    for pattern, replacement in LEGAL_FORM_PATTERNS:
        s = re.sub(r'\s*' + pattern + r'\s*', replacement + ' ', s, flags=re.IGNORECASE)

    # Remove punctuation at word boundaries
    s = re.sub(r'[.,;:!?()"\'\-]+', ' ', s)

    # Normalize whitespace again
    s = " ".join(s.split())

    return s.strip()


def extract_search_words(name: str) -> List[str]:
    """
    Extract meaningful search words from a company name.

    Removes legal forms and returns individual words for fuzzy matching.
    Filters out very short words (< 2 chars) and common filler words.
    """
    normalized = normalize_company_name(name)

    # Split into words
    words = normalized.split()

    # Filter out short words and common fillers
    stop_words = {'und', 'der', 'die', 'das', 'für', 'mit', 'von', 'zur', 'zum', 'den', 'dem'}
    meaningful_words = [w for w in words if len(w) >= 2 and w not in stop_words]

    return meaningful_words


def normalize_string(s: Optional[str]) -> str:
    """Normalize string for comparison (legacy function for backward compat)."""
    return normalize_company_name(s)


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

    # Check if one contains the other (substring match)
    if s1 in s2 or s2 in s1:
        # Score based on length ratio
        shorter = min(len(s1), len(s2))
        longer = max(len(s1), len(s2))
        return 0.7 + (0.3 * shorter / longer)

    # Word overlap score (Jaccard similarity)
    words1 = set(s1.split())
    words2 = set(s2.split())
    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2

    if not intersection:
        return 0.0

    jaccard = len(intersection) / len(union)

    # Boost score if all words from the shorter set are in the longer set
    smaller_set = words1 if len(words1) <= len(words2) else words2
    if smaller_set <= (words1 | words2):
        coverage = len(intersection) / len(smaller_set)
        # If query words are fully covered, boost the score
        if coverage == 1.0:
            jaccard = max(jaccard, 0.8)

    return jaccard


def calculate_name_score(query_name: str, company_name: str) -> float:
    """
    Calculate name match score with word-based and normalized matching.

    Handles cases like:
    - "Wacker Fußball GmbH" vs "Wacker Burghausen Fußball GmbH" -> high score
    - "RAL gGmbH" vs "RAL gemeinnützige GmbH" -> high score
    """
    # Normalize both names
    query_normalized = normalize_company_name(query_name)
    company_normalized = normalize_company_name(company_name)

    # Exact match after normalization
    if query_normalized == company_normalized:
        return 1.0

    # Get words from both
    query_words = set(query_normalized.split())
    company_words = set(company_normalized.split())

    if not query_words or not company_words:
        return 0.0

    # Check how many query words are in the company name
    matched_words = query_words & company_words
    query_coverage = len(matched_words) / len(query_words) if query_words else 0

    # If all query words are found, it's a strong match
    if query_coverage == 1.0:
        # Score based on how specific the match is
        company_coverage = len(matched_words) / len(company_words)
        # All query words match, score between 0.85 and 1.0 based on specificity
        return 0.85 + (0.15 * company_coverage)

    # Partial match
    if matched_words:
        # At least some words match
        return 0.5 + (0.35 * query_coverage)

    # Check substring matching as fallback
    return calculate_similarity(query_normalized, company_normalized)


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

    # Name matching using improved word-based scoring
    if query.name:
        company_name = company.legal_name or company.raw_name or ""
        name_score = calculate_name_score(query.name, company_name)
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

    # Domain matching - use normalized domain field from database
    if query.domain or query.email:
        query_domain = extract_domain(query.domain) or extract_domain(query.email)
        if query_domain:
            # Use the pre-computed domain field from the company record
            company_domain = company.domain
            if company_domain and query_domain:
                scores['domain'] = 1.0 if query_domain == company_domain else 0.0
            else:
                scores['domain'] = 0.0

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


async def search_stage(
    db: AsyncSession,
    name_words: List[str],
    city: Optional[str],
    postal_code: Optional[str],
    query_domain: Optional[str],
    use_name: bool = True,
    use_domain: bool = True,
    limit: int = 100
) -> List[Company]:
    """
    Execute a single search stage with given parameters.

    Args:
        name_words: List of words to search in company name
        city: City to filter by
        postal_code: Postal code prefix to filter by
        query_domain: Domain to filter by
        use_name: Whether to include name conditions
        use_domain: Whether to include domain condition
        limit: Maximum results to return
    """
    conditions = []

    # Name word matching - each word must appear somewhere
    if use_name and name_words:
        name_conditions = []
        for word in name_words:
            word_pattern = f"%{word}%"
            name_conditions.append(
                or_(
                    Company.raw_name.ilike(word_pattern),
                    Company.legal_name.ilike(word_pattern)
                )
            )
        # All words must match (AND logic for words)
        conditions.extend(name_conditions)

    # Location filters
    if city:
        conditions.append(Company.address_city.ilike(f"%{city}%"))

    if postal_code:
        conditions.append(Company.address_postal_code.ilike(f"{postal_code}%"))

    # Domain filter
    if use_domain and query_domain:
        conditions.append(Company.domain == query_domain)

    if not conditions:
        return []

    db_query = select(Company).where(and_(*conditions)).limit(limit)
    result = await db.execute(db_query)
    return list(result.scalars().all())


@router.post("/match", response_model=MatchResponse)
async def match_companies(
    request: MatchRequest,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key)
):
    """
    Find matching companies based on provided criteria.

    Uses a multi-stage fallback strategy:
    - Stage 1: Name words + City + PLZ + Domain (strictest)
    - Stage 2: Name words + City + PLZ (without domain)
    - Stage 3: Domain + City + PLZ (without name - domain as primary identifier)

    Returns companies sorted by match score with detailed scoring breakdown.
    """
    query = request.query
    options = request.options or MatchOptions()

    # Validate at least one search criterion
    has_name = bool(query.name)
    has_location = bool(query.city or query.postal_code)
    query_domain = extract_domain(query.domain) or extract_domain(query.email)
    has_domain = bool(query_domain)

    if not has_name and not has_location and not has_domain:
        raise HTTPException(
            status_code=400,
            detail="At least one search criterion (name, city, postal_code, domain, or email) is required"
        )

    # Extract search words from name
    name_words = extract_search_words(query.name) if query.name else []

    # Track seen company IDs to avoid duplicates across stages
    seen_ids: Set[str] = set()
    all_companies: List[Company] = []

    # Stage 1: Name + City + PLZ + Domain (strictest match)
    if name_words and has_domain:
        logger.debug("Stage 1: Name words + Location + Domain")
        stage1_results = await search_stage(
            db, name_words, query.city, query.postal_code, query_domain,
            use_name=True, use_domain=True
        )
        for c in stage1_results:
            if c.company_id not in seen_ids:
                seen_ids.add(c.company_id)
                all_companies.append(c)

    # Stage 2: Name + City + PLZ (without domain)
    if name_words:
        logger.debug("Stage 2: Name words + Location (no domain)")
        stage2_results = await search_stage(
            db, name_words, query.city, query.postal_code, query_domain,
            use_name=True, use_domain=False
        )
        for c in stage2_results:
            if c.company_id not in seen_ids:
                seen_ids.add(c.company_id)
                all_companies.append(c)

    # Stage 3: Domain + City + PLZ (domain as primary identifier, no name)
    if has_domain and (not name_words or len(all_companies) < 5):
        logger.debug("Stage 3: Domain + Location (no name)")
        stage3_results = await search_stage(
            db, [], query.city, query.postal_code, query_domain,
            use_name=False, use_domain=True
        )
        for c in stage3_results:
            if c.company_id not in seen_ids:
                seen_ids.add(c.company_id)
                all_companies.append(c)

    logger.info(f"Found {len(all_companies)} companies across all search stages")

    # Score and rank results
    scored_results = []
    for company in all_companies:
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
                email=company.email,
                website=company.website,
                domain=company.domain,
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
            "contact": {
                "email": company.email,
                "website": company.website,
                "phone": company.phone,
                "domain": company.domain
            },
            "last_update_time": company.last_update_time.isoformat() if company.last_update_time else None,
            "full_record": company.full_record
        }
    }


# Employee API Models
class EmployeeAddress(BaseModel):
    street: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None


class EmployeePosition(BaseModel):
    type: Optional[str] = None
    description: Optional[str] = None
    date: Optional[str] = None


class Employee(BaseModel):
    person_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    birth_date: Optional[str] = None
    address: EmployeeAddress
    position: EmployeePosition
    is_active: bool


class CompanyEmployeesResponse(BaseModel):
    success: bool
    company_id: str
    company_name: Optional[str] = None
    employees: List[Employee]
    total: int
    active_count: int
    inactive_count: int


def determine_employee_status(related_person: dict) -> bool:
    """
    Determine if an employee is currently active in their position.

    Returns True if active, False if inactive.

    Logic:
    1. Check if description starts with "ehem." (former) -> inactive
    2. Check the last role entry - if it has "demotion: true" -> inactive
    3. Otherwise -> active
    """
    description = related_person.get("description", "")

    # Check for "ehem." (ehemaliger/ehemalige = former)
    if description and description.lower().startswith("ehem."):
        return False

    # Check roles for demotion flag
    roles = related_person.get("roles", [])
    if roles:
        # Get the last role entry (most recent)
        last_role = roles[-1]
        if last_role.get("demotion", False):
            return False

    return True


def extract_employee_from_related_person(related_person: dict) -> Employee:
    """Extract employee data from a relatedPersons item."""
    person_data = related_person.get("person", {})
    address_data = person_data.get("address", {})
    name_data = person_data.get("name", {})
    roles = related_person.get("roles", [])

    # Get the most recent active role (or last role if all are demotions)
    current_role = None
    for role in reversed(roles):
        if not role.get("demotion", False):
            current_role = role
            break

    # If no active role found, use the last role before demotion
    if current_role is None and roles:
        # Find the last non-demotion role
        for role in reversed(roles):
            if role.get("demotion", False):
                continue
            current_role = role
            break
        # If still none, just use the first role
        if current_role is None:
            current_role = roles[0] if roles else {}

    return Employee(
        person_id=person_data.get("id", ""),
        first_name=name_data.get("firstName"),
        last_name=name_data.get("lastName"),
        birth_date=person_data.get("birthDate"),
        address=EmployeeAddress(
            street=address_data.get("street") or None,
            postal_code=address_data.get("postalCode") or None,
            city=address_data.get("city") or None,
            state=address_data.get("state") or None,
            country=address_data.get("country") or None,
        ),
        position=EmployeePosition(
            type=current_role.get("type") if current_role else related_person.get("description"),
            description=related_person.get("description"),
            date=current_role.get("date") if current_role else None,
        ),
        is_active=determine_employee_status(related_person)
    )


@router.get("/company/{company_id}/employees", response_model=CompanyEmployeesResponse)
async def get_company_employees(
    company_id: str,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key)
):
    """
    Get all employees (related persons) for a company.

    Returns employee details including:
    - Personal info (name, birth date)
    - Address
    - Position/role
    - Active/inactive status

    The active status is determined by:
    1. If description starts with "ehem." (former) -> inactive
    2. If the last role has "demotion: true" -> inactive
    3. Otherwise -> active
    """
    result = await db.execute(
        select(Company).where(Company.company_id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Extract employees from full_record
    full_record = company.full_record or {}
    related_persons = full_record.get("relatedPersons", {}).get("items", [])

    employees = []
    active_count = 0
    inactive_count = 0

    for rp in related_persons:
        employee = extract_employee_from_related_person(rp)
        employees.append(employee)

        if employee.is_active:
            active_count += 1
        else:
            inactive_count += 1

    return CompanyEmployeesResponse(
        success=True,
        company_id=company.company_id,
        company_name=company.legal_name or company.raw_name,
        employees=employees,
        total=len(employees),
        active_count=active_count,
        inactive_count=inactive_count
    )
