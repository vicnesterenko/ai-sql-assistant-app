"""API-маршрути для перевірки стану застосунку та його залежностей."""

import time

from fastapi import APIRouter, Response, status

from app.db.pool import get_pool
from app.models.types import HealthResponse
from app.core.logger_setup import logger


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    """Перевіряє, чи запущений і відповідає процес FastAPI."""

    return HealthResponse(
        status="ok",
        message="Application is running",
        db_connected=None,
        sample_query_latency_ms=None,
    )


@router.get("/ready", response_model=HealthResponse)
async def readiness(response: Response) -> HealthResponse:
    """Перевіряє готовність застосунку працювати з PostgreSQL."""

    started = time.perf_counter()

    try:
        pool = get_pool()

        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

        # затримка, тобто час між початком операції та отриманням результату.
        latency_ms = int((time.perf_counter() - started) * 1000)

        return HealthResponse(
            status="ok",
            message="Application is ready",
            db_connected=True,
            sample_query_latency_ms=latency_ms,
        )

    except Exception as e:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.exception(exc_info=str(e))

        return HealthResponse(
            status="degraded",
            message="Database connection failed",
            db_connected=False,
            sample_query_latency_ms=None,
        )