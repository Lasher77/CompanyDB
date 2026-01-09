from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from ..database import get_db
from ..opensearch_client import get_opensearch_client
from ..schemas import HealthResponse
from ..config import settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Check health of all services."""
    postgres_status = "error"
    opensearch_status = "disabled"

    # Check PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        postgres_status = "ok"
    except Exception as e:
        postgres_status = f"error: {str(e)}"

    # Check OpenSearch (if enabled)
    if settings.opensearch_enabled:
        try:
            client = get_opensearch_client()
            info = client.info()
            opensearch_status = f"ok (version {info['version']['number']})"
        except Exception as e:
            opensearch_status = f"error: {str(e)}"

    # Overall status: ok if postgres is ok (opensearch is optional)
    if postgres_status == "ok":
        if opensearch_status == "disabled" or opensearch_status.startswith("ok"):
            overall = "ok"
        else:
            overall = "degraded (opensearch unavailable)"
    else:
        overall = "error"

    return HealthResponse(
        status=overall,
        postgres=postgres_status,
        opensearch=opensearch_status
    )
