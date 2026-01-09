from pydantic import BaseModel
from datetime import datetime
from uuid import UUID


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
