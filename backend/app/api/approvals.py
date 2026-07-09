from fastapi import APIRouter, Depends, HTTPException

from app.core.security import CurrentUser, get_current_user, require_approver
from app.models.types import ApprovalItem, ApprovalListResponse, ApproveRequest, RejectRequest
from app.services.approval_orchestrator import (
    approve_and_resume,
    get_approval_with_expiry,
    list_approvals_with_expiry,
    reject_and_resume,
)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("", response_model=ApprovalListResponse)
async def list_approval_endpoint(
    status: str = "pending", user: CurrentUser = Depends(get_current_user)
) -> ApprovalListResponse:
    require_approver(user)
    items, total = await list_approvals_with_expiry(status)
    return ApprovalListResponse(items=[ApprovalItem.model_validate(x) for x in items], total=total)


@router.get("/{approval_id}", response_model=ApprovalItem)
async def get_approval_endpoint(approval_id: str, user: CurrentUser = Depends(get_current_user)) -> ApprovalItem:
    item = await get_approval_with_expiry(approval_id)
    if not item:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return ApprovalItem.model_validate(item)


@router.post("/{approval_id}/approve")
async def approve_endpoint(approval_id: str, payload: ApproveRequest, user: CurrentUser = Depends(get_current_user)):
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


@router.post("/{approval_id}/reject")
async def reject_endpoint(approval_id: str, payload: RejectRequest, user: CurrentUser = Depends(get_current_user)):
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
