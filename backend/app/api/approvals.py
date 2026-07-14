"""
approvals.py — це транспортний API-шар human-in-the-loop механізму.
Він не виконує SQL самостійно,
а перевіряє автентифікацію та роль approver, валідовує request body через Pydantic
і передає виконання в approval_orchestrator.
Після approve або reject оркестратор відновлює призупинений LangGraph workflow та повертає його фінальну відповідь.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import CurrentUser, get_current_user, require_approver
from app.models.types import ApprovalItem, ApprovalListResponse, ApproveRequest, RejectRequest
from app.services.approval_orchestrator import (
    approve_and_resume,
    get_approval_with_expiry,
    list_approvals_with_expiry,
    reject_and_resume,
)


"""API-маршрути для перегляду, погодження та відхилення ризикових SQL-запитів"""
router = APIRouter(prefix="/api/approvals", tags=["approvals"])

# отримання списку approval-запитів - GET /api/approvals?status=pending
@router.get("", response_model=ApprovalListResponse)
async def list_approval_endpoint(
    status: str = "pending", user: CurrentUser = Depends(get_current_user)
) -> ApprovalListResponse:
    """Повертає список SQL-запитів на погодження за вказаним статусом."""
    require_approver(user)
    items, total = await list_approvals_with_expiry(status)
    return ApprovalListResponse(items=[ApprovalItem.model_validate(x) for x in items], total=total)

# отримання одного approval - GET /api/approvals/approval-123
async def get_approval_endpoint(
    approval_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> ApprovalItem:
    """Повертає запит на погодження за його ідентифікатором."""

    require_approver(user)

    item = await get_approval_with_expiry(approval_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail="Approval request not found",
        )

    return ApprovalItem.model_validate(item)

# Підтвердження SQL-запиту - POST /api/approvals/approval-123/approve
@router.post("/{approval_id}/approve")
async def approve_endpoint(approval_id: str, payload: ApproveRequest, user: CurrentUser = Depends(get_current_user)):
    """Погоджує SQL-запит і відновлює виконання призупиненого workflow."""
    require_approver(user)
    item, final_state = await approve_and_resume(approval_id, user.email, payload.modified_sql)
    if not item:
        raise HTTPException(status_code=404, detail="Pending approval request not found")
    return {
        "approval_id": approval_id,
        "status": "approved",
        "response": final_state.final_response.model_dump(mode="json")
        if final_state and final_state.final_response
        else None,
    }

# Відхилення SQL-запиту - POST /api/approvals/approval-123/reject
@router.post("/{approval_id}/reject")
async def reject_endpoint(approval_id: str, payload: RejectRequest, user: CurrentUser = Depends(get_current_user)):
    """Відхиляє SQL-запит і відновлює workflow з причиною відмови."""
    require_approver(user)
    item, final_state = await reject_and_resume(approval_id, user.email, payload.reason)
    if not item:
        raise HTTPException(status_code=404, detail="Pending approval request not found")
    return {
        "approval_id": approval_id,
        "status": "rejected",
        "response": final_state.final_response.model_dump(mode="json")
        if final_state and final_state.final_response
        else None,
    }
