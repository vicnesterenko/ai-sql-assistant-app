import time

from app.core.logger_setup import log_event
from app.core.settings import settings
from app.db.pool import get_pool
from app.models.types import ApprovalDecision, ApprovalStatus
from app.resources.sql_query import (
    APPROVE_APPROVAL_SQL,
    COUNT_APPROVALS_BY_STATUS_SQL,
    CREATE_APPROVAL_REQUEST_SQL,
    EXPIRE_OLD_PENDING_SQL,
    GET_APPROVAL_SQL,
    LIST_APPROVALS_SQL,
    REJECT_APPROVAL_SQL,
)


async def expire_old_pending() -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(EXPIRE_OLD_PENDING_SQL, settings.approval_timeout_minutes)
    for row in rows:
        log_event("approval.expired", approval_id=row["id"], session_id=row["session_id"], thread_id=row["thread_id"])
    return [dict(row) for row in rows]


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
            CREATE_APPROVAL_REQUEST_SQL,
            session_id,
            thread_id,
            requester_email,
            question,
            generated_sql,
            risk_level,
            risk_justification,
        )
    log_event(
        "approval.created",
        approval_id=row["id"],
        session_id=session_id,
        thread_id=thread_id,
        requester_email=requester_email,
    )
    return row["id"]


async def get_approval(approval_id: str) -> dict | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(GET_APPROVAL_SQL, approval_id)
    return dict(row) if row else None


async def list_approvals(status: str = "pending") -> tuple[list[dict], int]:
    pool = get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval(COUNT_APPROVALS_BY_STATUS_SQL, status)
        rows = await conn.fetch(LIST_APPROVALS_SQL, status)
    return [dict(row) for row in rows], int(total or 0)


async def approve(approval_id: str, approver_email: str, modified_sql: str | None) -> dict | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(APPROVE_APPROVAL_SQL, approval_id, approver_email, modified_sql)
    if row:
        duration_ms = int((time.time() - row["created_at"].timestamp()) * 1000)
        log_event(
            "approval.approved",
            approval_id=approval_id,
            approver_email=approver_email,
            duration_from_request_ms=duration_ms,
        )
        item = dict(row)
        item["created_at"] = item.pop("created_at_text")
        return item
    return None


async def reject(approval_id: str, approver_email: str, reason: str) -> dict | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(REJECT_APPROVAL_SQL, approval_id, approver_email, reason)
    if row:
        duration_ms = int((time.time() - row["created_at"].timestamp()) * 1000)
        log_event(
            "approval.rejected",
            approval_id=approval_id,
            approver_email=approver_email,
            duration_from_request_ms=duration_ms,
        )
        item = dict(row)
        item["created_at"] = item.pop("created_at_text")
        return item
    return None


def decision_from_row(row: dict) -> ApprovalDecision:
    status = ApprovalStatus(row["status"])
    return ApprovalDecision(
        status=status,
        approver_email=row.get("approver_email"),
        modified_sql=row.get("approved_sql"),
        rejection_reason=row.get("rejection_reason"),
    )
