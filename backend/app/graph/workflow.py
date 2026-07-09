"""
Approver approves/rejects
↓
resume_after_approval()
↓
load_state або rebuild state по approval_id
↓
await_approval
↓
if approved:
    execute_query
    ↓
    format_result
↓
if rejected:
    format_result з rejection message
"""

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.graph.state import SQLAssistantStateDict
from app.graph.nodes import (
    assess_risk_node,
    await_approval_node,
    execute_query_node,
    format_result_node,
    generate_sql_node,
    handle_error_node,
    parse_intent_node,
    request_approval_node,
    validate_sql_node,
)
from app.models.types import ApprovalDecision, ApprovalStatus, Intent, RiskLevel, SQLAssistantState
from app.services.approval_service import decision_from_row, get_approval
from app.services.audit_service import get_audit_by_approval_request
from app.services.session_service import recent_context
from app.services.state_store import load_state, save_state


def _obj_value(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def route_validation(state: SQLAssistantStateDict) -> str:
    validation = state.get("validation_result")
    if validation and _obj_value(validation, "is_valid"):
        return "valid"
    if state.get("retry_count", 0) <= 2:
        return "retry"
    return "error"


def route_risk(state: SQLAssistantStateDict) -> str:
    risk = state.get("risk_level")
    risk_value = risk.value if hasattr(risk, "value") else risk
    if risk_value == "HIGH":
        return "high"
    return "execute"


def route_approval(state: SQLAssistantStateDict) -> str:
    decision = state.get("approval_decision")
    if not decision:
        return "wait"
    status = _obj_value(decision, "status")
    status_value = status.value if hasattr(status, "value") else status
    if status_value == ApprovalStatus.APPROVED.value:
        return "approved"
    return "rejected"


def route_execution(state: SQLAssistantStateDict) -> str:
    result = state.get("execution_result")
    if result and _obj_value(result, "status") == "ok":
        return "ok"
    if state.get("execution_retry_count", 0) <= 1:
        return "retry"
    return "done"


builder = StateGraph(SQLAssistantStateDict)

builder.add_node("parse_intent", parse_intent_node)
builder.add_node("generate_sql", generate_sql_node)
builder.add_node("validate_sql", validate_sql_node)
builder.add_node("assess_risk", assess_risk_node)
builder.add_node("request_approval", request_approval_node)
builder.add_node("await_approval", await_approval_node)
builder.add_node("execute_query", execute_query_node)
builder.add_node("format_result", format_result_node)
builder.add_node("handle_error", handle_error_node)

builder.set_entry_point("parse_intent")
builder.add_edge("parse_intent", "generate_sql")
builder.add_edge("generate_sql", "validate_sql")
builder.add_conditional_edges(
    "validate_sql",
    route_validation,
    {"valid": "assess_risk", "retry": "generate_sql", "error": "handle_error"}
)
builder.add_conditional_edges(
    "assess_risk",
    route_risk,
    {"execute": "execute_query", "high": "request_approval"}
)
builder.add_edge("request_approval", "await_approval")
builder.add_conditional_edges(
    "await_approval",
    route_approval,
    {"wait": END, "approved": "execute_query", "rejected": "format_result"}
)
builder.add_conditional_edges(
    "execute_query",
    route_execution,
    {"ok": "format_result", "retry": "generate_sql", "done": "format_result"}
)
builder.add_edge("format_result", END)
builder.add_edge("handle_error", END)

compiled_graph = builder.compile(checkpointer=MemorySaver())

resume_builder = StateGraph(SQLAssistantStateDict)
resume_builder.add_node("await_approval", await_approval_node)
resume_builder.add_node("execute_query", execute_query_node)
resume_builder.add_node("generate_sql", generate_sql_node)
resume_builder.add_node("validate_sql", validate_sql_node)
resume_builder.add_node("assess_risk", assess_risk_node)
resume_builder.add_node("request_approval", request_approval_node)
resume_builder.add_node("format_result", format_result_node)
resume_builder.add_node("handle_error", handle_error_node)
resume_builder.set_entry_point("await_approval")
resume_builder.add_conditional_edges(
    "await_approval",
    route_approval,
    {"wait": END, "approved": "execute_query", "rejected": "format_result"}
)
resume_builder.add_conditional_edges(
    "execute_query",
    route_execution,
    {"ok": "format_result", "retry": "generate_sql", "done": "format_result"}
)
resume_builder.add_edge("generate_sql", "validate_sql")
resume_builder.add_conditional_edges(
    "validate_sql",
    route_validation,
    {"valid": "assess_risk", "retry": "generate_sql", "error": "handle_error"}
)
resume_builder.add_conditional_edges(
    "assess_risk",
    route_risk,
    {"execute": "execute_query", "high": "request_approval"}
)
resume_builder.add_edge("request_approval", "await_approval")
resume_builder.add_edge("format_result", END)
resume_builder.add_edge("handle_error", END)

compiled_resume_graph = resume_builder.compile(checkpointer=MemorySaver())


async def run_message_graph(session_id: str, thread_id: str, requester_email: str, message: str) -> SQLAssistantState:
    history = await recent_context(session_id)
    state = SQLAssistantState(
        session_id=session_id,
        thread_id=thread_id,
        requester_email=requester_email,
        messages=history,
        current_question=message,
    )
    result = await compiled_graph.ainvoke(
        state.model_dump(),
        config={
            "configurable":
                {
                    "thread_id": f"{session_id}:{thread_id}"
                }
        },
    )
    final_state = SQLAssistantState.model_validate(result)
    await save_state(final_state)
    return final_state


async def _rebuild_state_from_approval_row(approval: dict, decision: ApprovalDecision) -> SQLAssistantState:
    """Rebuild enough graph state to resume a specific approval request.

    The normal path loads the persisted graph state from graph_state_snapshots.
    However, users may create several HIGH-risk requests in the same session/thread
    before an approver acts. A single session/thread snapshot can then point to the
    latest pending request, not necessarily the one the approver clicked.

    This fallback reconstructs the state from sql_approval_queue + sql_query_audit
    and keeps approval resumption deterministic per approval_id.
    """
    audit = await get_audit_by_approval_request(approval["id"])
    try:
        risk_level = RiskLevel(approval.get("risk_level") or RiskLevel.HIGH.value)
    except ValueError:
        risk_level = RiskLevel.HIGH

    return SQLAssistantState(
        session_id=approval["session_id"],
        thread_id=approval["thread_id"],
        requester_email=approval["requester_email"],
        messages=[],
        current_question=approval["original_question"],
        intent=Intent(question=approval["original_question"], is_follow_up=False, assumptions=[]),
        generated_sql=approval["generated_sql"],
        risk_level=risk_level,
        risk_justification=approval.get("risk_justification"),
        approval_request_id=approval["id"],
        approval_decision=decision,
        audit_id=audit["id"] if audit else None,
    )


async def resume_after_approval(approval_id: str) -> SQLAssistantState | None:
    approval = await get_approval(approval_id)
    if not approval:
        return None

    decision: ApprovalDecision = decision_from_row(approval)
    state = await load_state(approval["session_id"], approval["thread_id"])

    if not state or state.approval_request_id != approval_id:
        state = await _rebuild_state_from_approval_row(approval, decision)

    updated = state.model_copy(
        update={
            "approval_decision": decision,
            "final_response": None,
            "execution_result": None,
            "approved_sql": None,
            "error": None,
        }
    )
    result = await compiled_resume_graph.ainvoke(
        updated.model_dump(),
        config={
            "configurable":
                {
                    "thread_id":
                        f"{updated.session_id}:{updated.thread_id}:{approval_id}"
                }
        },
    )
    final_state = SQLAssistantState.model_validate(result)
    await save_state(final_state)
    return final_state
