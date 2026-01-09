import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, Integer, ForeignKey, DateTime, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .database import Base


class ImportJob(Base):
    __tablename__ = "import_job"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/running/completed/failed
    total_lines: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_lines: Mapped[int] = mapped_column(Integer, default=0)
    companies_imported: Mapped[int] = mapped_column(Integer, default=0)
    persons_imported: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class Company(Base):
    __tablename__ = "company"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("import_job.id"), nullable=True)
    company_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    raw_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_form: Mapped[str | None] = mapped_column(Text, nullable=True)  # Can be long
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    terminated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    register_unique_key: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    register_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_city: Mapped[str | None] = mapped_column(Text, nullable=True)  # Can contain unexpected data
    address_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_country: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Contact fields
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)  # Normalized domain for search
    last_update_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    full_record: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    persons: Mapped[list["CompanyPerson"]] = relationship("CompanyPerson", back_populates="company")


class Person(Base):
    __tablename__ = "person"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    first_name: Mapped[str | None] = mapped_column(Text, nullable=True)  # Can be long/unusual
    last_name: Mapped[str | None] = mapped_column(Text, nullable=True)   # Can be long/unusual
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    address_city: Mapped[str | None] = mapped_column(Text, nullable=True)  # Can contain unexpected data
    full_record: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    companies: Mapped[list["CompanyPerson"]] = relationship("CompanyPerson", back_populates="person")


class CompanyPerson(Base):
    __tablename__ = "company_person"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_db_id: Mapped[int] = mapped_column(Integer, ForeignKey("company.id"), nullable=False)
    person_db_id: Mapped[int] = mapped_column(Integer, ForeignKey("person.id"), nullable=False)
    role_type: Mapped[str | None] = mapped_column(Text, nullable=True)  # Can be long
    role_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    role_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="persons")
    person: Mapped["Person"] = relationship("Person", back_populates="companies")
