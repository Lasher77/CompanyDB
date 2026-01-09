from pydantic import BaseModel
from datetime import datetime, date
from uuid import UUID
from typing import Any


class ImportFileInfo(BaseModel):
    filename: str
    size_bytes: int
    size_human: str


class ImportJobCreate(BaseModel):
    filename: str


class ImportJobResponse(BaseModel):
    id: UUID
    filename: str
    status: str
    total_lines: int | None
    processed_lines: int
    companies_imported: int
    persons_imported: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str
    postgres: str
    opensearch: str


# Company schemas
class CompanyListItem(BaseModel):
    id: int
    company_id: str
    raw_name: str | None
    legal_name: str | None
    legal_form: str | None
    status: str | None
    terminated: bool | None
    address_city: str | None
    address_country: str | None
    register_id: str | None


class CompanyListResponse(BaseModel):
    items: list[CompanyListItem]
    total: int
    limit: int
    offset: int


class CompanyPersonRole(BaseModel):
    person_id: str
    first_name: str | None
    last_name: str | None
    role_type: str | None
    role_description: str | None
    role_date: date | None


class CompanyDetailResponse(BaseModel):
    id: int
    company_id: str
    raw_name: str | None
    legal_name: str | None
    legal_form: str | None
    status: str | None
    terminated: bool | None
    register_unique_key: str | None
    register_id: str | None
    address_city: str | None
    address_postal_code: str | None
    address_country: str | None
    last_update_time: datetime | None
    full_record: dict[str, Any]
    related_persons: list[CompanyPersonRole]
    created_at: datetime


# Person schemas
class PersonListItem(BaseModel):
    id: int
    person_id: str
    first_name: str | None
    last_name: str | None
    birth_year: int | None
    address_city: str | None


class PersonListResponse(BaseModel):
    items: list[PersonListItem]
    total: int
    limit: int
    offset: int


class PersonCompanyRole(BaseModel):
    company_id: str
    legal_name: str | None
    raw_name: str | None
    status: str | None
    role_type: str | None
    role_description: str | None
    role_date: date | None


class PersonDetailResponse(BaseModel):
    id: int
    person_id: str
    first_name: str | None
    last_name: str | None
    birth_year: int | None
    address_city: str | None
    full_record: dict[str, Any]
    related_companies: list[PersonCompanyRole]
    created_at: datetime
