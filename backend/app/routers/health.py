from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from ..database import get_db
from ..opensearch_client import get_opensearch_client
from ..schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Check health of all services."""
    postgres_status = "error"
    opensearch_status = "error"

    # Check PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        postgres_status = "ok"
    except Exception as e:
        postgres_status = f"error: {str(e)}"

    # Check OpenSearch
    try:
        client = get_opensearch_client()
        info = client.info()
        opensearch_status = f"ok (version {info['version']['number']})"
    except Exception as e:
        opensearch_status = f"error: {str(e)}"

    overall = "ok" if postgres_status == "ok" and opensearch_status.startswith("ok") else "degraded"

    return HealthResponse(
        status=overall,
        postgres=postgres_status,
        opensearch=opensearch_status
    )
