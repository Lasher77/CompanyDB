# Database Migrations

## How to run migrations

### Manual execution (PostgreSQL)

```bash
# Start PostgreSQL (if using Docker)
docker-compose up -d postgres

# Run the migration
PGPASSWORD=companydb psql -h localhost -p 5432 -U companydb -d companydb -f migrations/001_add_contact_fields_to_company.sql
```

### Using the setup script

```bash
cd backend
python -c "
from sqlalchemy import create_engine, text
from app.config import settings

engine = create_engine(settings.database_url_sync)
with engine.connect() as conn:
    with open('../migrations/001_add_contact_fields_to_company.sql', 'r') as f:
        conn.execute(text(f.read()))
    conn.commit()
print('Migration completed successfully')
"
```

## Migration History

### 001_add_contact_fields_to_company.sql
- **Date**: 2026-01-10
- **Purpose**: Add email, website, phone, and domain columns to company table
- **Impact**: Allows storing and searching company contact information
- **Required**: Yes (for optimized import to work properly)

## Future: Alembic Setup

For production, consider setting up Alembic for automated migrations:

```bash
pip install alembic
alembic init alembic
# Configure alembic.ini and env.py
# Create migrations with: alembic revision --autogenerate -m "description"
# Run migrations with: alembic upgrade head
```
