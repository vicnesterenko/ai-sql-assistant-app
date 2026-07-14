from app.graph.workflow import resume_after_approval
from app.graph.state import SQLAssistantState
from app.services import approval_service
from app.services.session_service import resolve_pending_approval_message


async def resume_and_notify(approval_id: str) -> SQLAssistantState | None:
    final_state = await resume_after_approval(approval_id)
    if final_state and final_state.final_response:
        await resolve_pending_approval_message(
            session_id=final_state.session_id,
            thread_id=final_state.thread_id,
            approval_id=approval_id,
            response=final_state.final_response,
        )
    return final_state


async def expire_overdue_and_notify() -> None:
    expired = await approval_service.expire_old_pending()
    for row in expired:
        await resume_and_notify(row["id"])


async def get_approval_with_expiry(approval_id: str) -> dict | None:
    await expire_overdue_and_notify()
    return await approval_service.get_approval(approval_id)


async def list_approvals_with_expiry(status: str = "pending") -> tuple[list[dict], int]:
    await expire_overdue_and_notify()
    return await approval_service.list_approvals(status)


async def approve_and_resume(
    approval_id: str,
    approver_email: str,
    modified_sql: str | None,
) -> tuple[dict | None, SQLAssistantState | None]:
    item = await approval_service.approve(approval_id, approver_email, modified_sql)
    if not item:
        return None, None
    final_state = await resume_and_notify(approval_id)
    return item, final_state


async def reject_and_resume(approval_id: str, approver_email: str, reason: str) -> tuple[dict | None, SQLAssistantState | None]:
    item = await approval_service.reject(approval_id, approver_email, reason)
    if not item:
        return None, None
    final_state = await resume_and_notify(approval_id)
    return item, final_state
