from fastapi import APIRouter, Depends, HTTPException

from app.core.security import CurrentUser, get_current_user, require_approver
from app.graph.workflow import resume_after_approval
from app.models.types import ApprovalItem, ApprovalListResponse, ApproveRequest, RejectRequest
from app.services.approval_service import approve, get_approval, list_approvals, reject
from app.services.session_service import resolve_pending_approval_message

router = APIRouter(prefix='/api/approvals', tags=['approvals'])


@router.get('', response_model=ApprovalListResponse)
async def list_approval_endpoint(status: str = 'pending', user: CurrentUser = Depends(get_current_user)) -> ApprovalListResponse:
    require_approver(user)
    items, total = await list_approvals(status)
    return ApprovalListResponse(items=[ApprovalItem.model_validate(x) for x in items], total=total)


@router.get('/{approval_id}', response_model=ApprovalItem)
async def get_approval_endpoint(approval_id: str, user: CurrentUser = Depends(get_current_user)) -> ApprovalItem:
    item = await get_approval(approval_id)
    if not item:
        raise HTTPException(status_code=404, detail='Approval request not found')
    return ApprovalItem.model_validate(item)


@router.post('/{approval_id}/approve')
async def approve_endpoint(approval_id: str, payload: ApproveRequest, user: CurrentUser = Depends(get_current_user)):
    require_approver(user)
    item = await approve(approval_id, user.email, payload.modified_sql)
    if not item:
        raise HTTPException(status_code=404, detail='Pending approval request not found')
    final_state = await resume_after_approval(approval_id)
    if final_state and final_state.final_response:
        await resolve_pending_approval_message(final_state.session_id, final_state.thread_id, approval_id, final_state.final_response)
    return {'approval_id': approval_id, 'status': 'approved', 'response': final_state.final_response.model_dump(mode='json') if final_state and final_state.final_response else None}


@router.post('/{approval_id}/reject')
async def reject_endpoint(approval_id: str, payload: RejectRequest, user: CurrentUser = Depends(get_current_user)):
    require_approver(user)
    item = await reject(approval_id, user.email, payload.reason)
    if not item:
        raise HTTPException(status_code=404, detail='Pending approval request not found')
    final_state = await resume_after_approval(approval_id)
    if final_state and final_state.final_response:
        await resolve_pending_approval_message(final_state.session_id, final_state.thread_id, approval_id, final_state.final_response)
    return {'approval_id': approval_id, 'status': 'rejected', 'response': final_state.final_response.model_dump(mode='json') if final_state and final_state.final_response else None}
