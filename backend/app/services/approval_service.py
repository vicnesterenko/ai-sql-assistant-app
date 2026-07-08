import time
from app.core.logging import log_event
from app.core.settings import settings
from app.db.pool import get_pool
from app.models.types import ApprovalDecision, ApprovalStatus


async def expire_old_pending() -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''
            UPDATE sql_approval_queue
            SET status = 'expired', resolved_at = now(), rejection_reason = 'Approval timed out.'
            WHERE status = 'pending'
              AND created_at < now() - ($1::int || ' minutes')::interval
            RETURNING id::text, session_id, thread_id
            ''',
            settings.approval_timeout_minutes,
        )
    for row in rows:
        log_event('approval.expired', approval_id=row['id'], session_id=row['session_id'], thread_id=row['thread_id'])


async def create_approval_request(
    session_id: str,
    thread_id: str,
    requester_email: str,
    question: str,
    generated_sql: str,
    risk_level: str,
    risk_justification: str,
) -> str:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''
            INSERT INTO sql_approval_queue(session_id, thread_id, requester_email, original_question, generated_sql, risk_level, risk_justification)
            VALUES($1, $2, $3, $4, $5, $6, $7)
            RETURNING id::text
            ''',
            session_id, thread_id, requester_email, question, generated_sql, risk_level, risk_justification,
        )
    log_event('approval.created', approval_id=row['id'], session_id=session_id, thread_id=thread_id, requester_email=requester_email)
    return row['id']


async def get_approval(approval_id: str) -> dict | None:
    await expire_old_pending()
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''
            SELECT id::text, session_id, thread_id, requester_email, original_question, generated_sql,
                   risk_level, risk_justification, status, approver_email, approved_sql, rejection_reason,
                   created_at::text, resolved_at::text
            FROM sql_approval_queue WHERE id = $1::uuid
            ''',
            approval_id,
        )
    return dict(row) if row else None


async def list_approvals(status: str = 'pending') -> tuple[list[dict], int]:
    await expire_old_pending()
    pool = get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval('SELECT count(*) FROM sql_approval_queue WHERE status = $1', status)
        rows = await conn.fetch(
            '''
            SELECT id::text, session_id, thread_id, requester_email, original_question, generated_sql,
                   risk_level, risk_justification, status, approver_email, approved_sql, rejection_reason,
                   created_at::text, resolved_at::text
            FROM sql_approval_queue
            WHERE status = $1
            ORDER BY created_at ASC
            ''',
            status,
        )
    return [dict(row) for row in rows], int(total or 0)


async def approve(approval_id: str, approver_email: str, modified_sql: str | None) -> dict | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''
            UPDATE sql_approval_queue
            SET status = 'approved', approver_email = $2, approved_sql = COALESCE($3, generated_sql), resolved_at = now()
            WHERE id = $1::uuid AND status = 'pending'
            RETURNING id::text, session_id, thread_id, requester_email, original_question, generated_sql,
                      risk_level, risk_justification, status, approver_email, approved_sql, rejection_reason,
                      created_at, created_at::text AS created_at_text, resolved_at::text
            ''',
            approval_id, approver_email, modified_sql,
        )
    if row:
        duration_ms = int((time.time() - row['created_at'].timestamp()) * 1000)
        log_event('approval.approved', approval_id=approval_id, approver_email=approver_email, duration_from_request_ms=duration_ms)
        item = dict(row)
        item['created_at'] = item.pop('created_at_text')
        return item
    return None


async def reject(approval_id: str, approver_email: str, reason: str) -> dict | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''
            UPDATE sql_approval_queue
            SET status = 'rejected', approver_email = $2, rejection_reason = $3, resolved_at = now()
            WHERE id = $1::uuid AND status = 'pending'
            RETURNING id::text, session_id, thread_id, requester_email, original_question, generated_sql,
                      risk_level, risk_justification, status, approver_email, approved_sql, rejection_reason,
                      created_at, created_at::text AS created_at_text, resolved_at::text
            ''',
            approval_id, approver_email, reason,
        )
    if row:
        duration_ms = int((time.time() - row['created_at'].timestamp()) * 1000)
        log_event('approval.rejected', approval_id=approval_id, approver_email=approver_email, duration_from_request_ms=duration_ms)
        item = dict(row)
        item['created_at'] = item.pop('created_at_text')
        return item
    return None


def decision_from_row(row: dict) -> ApprovalDecision:
    status = ApprovalStatus(row['status'])
    return ApprovalDecision(
        status=status,
        approver_email=row.get('approver_email'),
        modified_sql=row.get('approved_sql'),
        rejection_reason=row.get('rejection_reason'),
    )
