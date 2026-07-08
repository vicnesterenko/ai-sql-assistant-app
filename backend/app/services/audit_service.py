from typing import Any
from app.db.pool import get_pool


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
            '''
            INSERT INTO sql_query_audit(session_id, thread_id, requester_email, question, generated_sql)
            VALUES($1, $2, $3, $4, $5)
            RETURNING id::text
            ''',
            session_id, thread_id, requester_email, question, generated_sql,
        )
    return row['id']


async def update_audit(audit_id: str, **fields: Any) -> None:
    if not fields:
        return
    allowed = {
        'generated_sql', 'final_sql', 'risk_level', 'approval_request_id', 'execution_status',
        'execution_duration_ms', 'row_count', 'error_message', 'result_summary'
    }
    updates = []
    values = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        values.append(value)
        updates.append(f'{key} = ${len(values)}')
    if not updates:
        return
    values.append(audit_id)
    query = f'UPDATE sql_query_audit SET {", ".join(updates)} WHERE id = ${len(values)}::uuid'
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(query, *values)


async def list_audit(session_id: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
    pool = get_pool()
    where = 'WHERE session_id = $1' if session_id else ''
    params = [session_id] if session_id else []
    async with pool.acquire() as conn:
        total = await conn.fetchval(f'SELECT count(*) FROM sql_query_audit {where}', *params)
        rows = await conn.fetch(
            f'''
            SELECT id::text, session_id, thread_id, requester_email, question, generated_sql, final_sql,
                   risk_level, approval_request_id::text, execution_status, execution_duration_ms,
                   row_count, error_message, result_summary, created_at::text
            FROM sql_query_audit
            {where}
            ORDER BY created_at DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            ''',
            *params, limit, offset,
        )
    return [dict(row) for row in rows], int(total or 0)


async def get_audit(audit_id: str) -> dict | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''
            SELECT id::text, session_id, thread_id, requester_email, question, generated_sql, final_sql,
                   risk_level, approval_request_id::text, execution_status, execution_duration_ms,
                   row_count, error_message, result_summary, created_at::text
            FROM sql_query_audit WHERE id = $1::uuid
            ''',
            audit_id,
        )
    return dict(row) if row else None

async def get_audit_by_approval_request(approval_id: str) -> dict | None:
    """Return the audit row attached to an approval request.

    This is used when resuming approval decisions. It also makes the resume path
    robust when several high-risk requests are pending in the same session/thread.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id::text, session_id, thread_id, requester_email, question, generated_sql, final_sql,
                   risk_level, approval_request_id::text, execution_status, execution_duration_ms,
                   row_count, error_message, result_summary, created_at::text
            FROM sql_query_audit
            WHERE approval_request_id = $1::uuid
            ORDER BY created_at DESC
            LIMIT 1
            """,
            approval_id,
        )
    return dict(row) if row else None

