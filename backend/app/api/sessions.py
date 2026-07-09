from fastapi import APIRouter, Depends, HTTPException, Response

from app.core.rate_limit import check_session_rate_limit
from app.core.security import CurrentUser, get_current_user
from app.graph.workflow import run_message_graph
from app.models.types import ChatMessageRequest, CreateSessionRequest, MessageRecord, SessionResponse
from app.services.session_service import create_session, delete_session, get_session, list_messages, save_message

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse)
async def create_session_endpoint(
    payload: CreateSessionRequest, user: CurrentUser = Depends(get_current_user)
) -> SessionResponse:
    row = await create_session(payload.requester_email or user.email)
    return SessionResponse(session_id=row["id"], created_at=row["created_at"])


@router.post("/{session_id}/messages")
async def post_message(session_id: str, payload: ChatMessageRequest, user: CurrentUser = Depends(get_current_user)):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    check_session_rate_limit(session_id)
    requester_email = session["requester_email"] or user.email

    await save_message(session_id, payload.thread_id, "user", payload.message)

    final_state = await run_message_graph(session_id, payload.thread_id, requester_email, payload.message)

    if not final_state.final_response:
        raise HTTPException(status_code=500, detail="Graph did not produce a response")
    await save_message(
        session_id=session_id,
        thread_id=payload.thread_id,
        role="assistant",
        content=final_state.final_response.message,
        response=final_state.final_response,
    )
    return {"response": final_state.final_response}


@router.get("/{session_id}/messages", response_model=dict)
async def get_messages(session_id: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"messages": [MessageRecord.model_validate(m) for m in await list_messages(session_id)]}


@router.delete("/{session_id}", status_code=204)
async def delete_session_endpoint(session_id: str) -> Response:
    await delete_session(session_id)
    return Response(status_code=204)
