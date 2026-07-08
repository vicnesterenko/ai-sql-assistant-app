import time
from fastapi import APIRouter
from app.db.pool import get_pool
from app.models.types import HealthResponse

router = APIRouter(tags=['health'])


@router.get('/health', response_model=HealthResponse)
async def health() -> HealthResponse:
    started = time.perf_counter()
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval('SELECT 1')
        latency = int((time.perf_counter() - started) * 1000)
        return HealthResponse(status='ok', db_connected=True, sample_query_latency_ms=latency)
    except Exception:
        return HealthResponse(status='degraded', db_connected=False, sample_query_latency_ms=None)
