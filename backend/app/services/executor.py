import asyncio
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from app.core.logger_setup import log_event
from app.core.settings import settings
from app.db.pool import get_pool
from app.models.types import ExecutionResult


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _strip_semicolon(sql: str) -> str:
    return sql.strip().rstrip(";")


async def execute_readonly_sql(sql: str, session_id: str, thread_id: str) -> ExecutionResult:
    pool = get_pool()
    started = time.perf_counter()
    timeout_ms = settings.query_timeout_seconds * 1000
    max_rows = settings.max_result_rows
    wrapped_sql = f"SELECT * FROM ({_strip_semicolon(sql)}) AS ai_query_result LIMIT {max_rows + 1}"

    try:
        async with pool.acquire() as conn:
            async with conn.transaction(readonly=True):
                await conn.execute(f"SET LOCAL statement_timeout = {timeout_ms}")
                rows = await asyncio.wait_for(conn.fetch(wrapped_sql), timeout=settings.query_timeout_seconds)

        duration_ms = int((time.perf_counter() - started) * 1000)
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        columns = list(rows[0].keys()) if rows else []
        payload = [{key: _jsonable(value) for key, value in dict(row).items()} for row in rows]

        log_event(
            message="db.query.executed",
            session_id=session_id,
            thread_id=thread_id,
            db_duration_ms=duration_ms,
            row_count=len(payload),
            truncated=truncated,
        )
        return ExecutionResult(
            status="ok",
            columns=columns,
            rows=payload,
            row_count=len(payload),
            truncated=truncated,
            duration_ms=duration_ms,
        )

    except (asyncio.TimeoutError, asyncpg.QueryCanceledError) as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        log_event(
            message="db.query.timeout",
            session_id=session_id,
            thread_id=thread_id,
            db_duration_ms=duration_ms,
            error=str(exc),
        )
        return ExecutionResult(
            status="timeout", duration_ms=duration_ms, error_message="Query timed out and was cancelled."
        )
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        log_event(
            message="db.query.error",
            session_id=session_id,
            thread_id=thread_id,
            db_duration_ms=duration_ms,
            error=str(exc),
        )
        return ExecutionResult(status="error", duration_ms=duration_ms, error_message=str(exc))
