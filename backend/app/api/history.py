from fastapi import APIRouter, HTTPException
from app.models.types import AuditEntry, AuditListResponse
from app.services.audit_service import get_audit, list_audit

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=AuditListResponse)
async def list_history(session_id: str | None = None, limit: int = 50, offset: int = 0) -> AuditListResponse:
    items, total = await list_audit(session_id=session_id, limit=limit, offset=offset)
    return AuditListResponse(items=[AuditEntry.model_validate(x) for x in items], total=total)


@router.get("/{audit_id}", response_model=AuditEntry)
async def get_history(audit_id: str) -> AuditEntry:
    item = await get_audit(audit_id)
    if not item:
        raise HTTPException(status_code=404, detail="Audit entry not found")
    return AuditEntry.model_validate(item)
