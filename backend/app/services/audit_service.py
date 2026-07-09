from typing import Any

from app.db.pool import get_pool
from app.resources.sql_query import (
    COUNT_AUDIT_ALL_SQL,
    COUNT_AUDIT_BY_SESSION_SQL,
    CREATE_AUDIT_SQL,
    GET_AUDIT_BY_APPROVAL_REQUEST_SQL,
    GET_AUDIT_SQL,
    LIST_AUDIT_ALL_SQL,
    LIST_AUDIT_BY_SESSION_SQL,
    build_update_audit_sql,
)


async def create_audit(
    session_id: str,
    thread_id: str,
    requester_email: str,
    question: str,
    generated_sql: str | None = None,
) -> str:
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            CREATE_AUDIT_SQL,
            session_id,
            thread_id,
            requester_email,
            question,
            generated_sql,
        )

    return row["id"]


async def update_audit(
    audit_id: str,
    *,
    generated_sql: str | None = None,
    final_sql: str | None = None,
    risk_level: str | None = None,
    approval_request_id: str | None = None,
    execution_status: str | None = None,
    execution_duration_ms: int | None = None,
    row_count: int | None = None,
    error_message: str | None = None,
    result_summary: str | None = None,
) -> None:
    fields: dict[str, Any] = {
        "generated_sql": generated_sql,
        "final_sql": final_sql,
        "risk_level": risk_level,
        "approval_request_id": approval_request_id,
        "execution_status": execution_status,
        "execution_duration_ms": execution_duration_ms,
        "row_count": row_count,
        "error_message": error_message,
        "result_summary": result_summary,
    }

    updates: list[str] = []
    values: list[Any] = []

    for key, value in fields.items():
        if value is None:
            continue

        values.append(value)
        updates.append(f"{key} = ${len(values)}")

    if not updates:
        return

    values.append(audit_id)

    query = build_update_audit_sql(
        updates=updates,
        audit_id_param_number=len(values),
    )

    pool = get_pool()

    async with pool.acquire() as conn:
        await conn.execute(query, *values)


async def list_audit(
    session_id: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    pool = get_pool()

    async with pool.acquire() as conn:
        if session_id:
            total = await conn.fetchval(
                COUNT_AUDIT_BY_SESSION_SQL,
                session_id,
            )
            rows = await conn.fetch(
                LIST_AUDIT_BY_SESSION_SQL,
                session_id,
                limit,
                offset,
            )
        else:
            total = await conn.fetchval(COUNT_AUDIT_ALL_SQL)
            rows = await conn.fetch(
                LIST_AUDIT_ALL_SQL,
                limit,
                offset,
            )

    return [dict(row) for row in rows], int(total or 0)


async def get_audit(audit_id: str) -> dict | None:
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            GET_AUDIT_SQL,
            audit_id,
        )

    return dict(row) if row else None


async def get_audit_by_approval_request(
    approval_id: str,
) -> dict | None:
    """Return the audit row attached to an approval request."""
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            GET_AUDIT_BY_APPROVAL_REQUEST_SQL,
            approval_id,
        )

    return dict(row) if row else None
