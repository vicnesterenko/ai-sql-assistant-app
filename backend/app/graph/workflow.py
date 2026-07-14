"""LangGraph workflow with PostgreSQL checkpoint persistence."""

from contextlib import AsyncExitStack
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from app.core.settings import settings
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
from app.graph.state import SQLAssistantState
from app.models.types import ApprovalStatus
from app.services.approval_service import decision_from_row, get_approval
from app.services.session_service import recent_context


_compiled_graph: Any | None = None
_workflow_resources: AsyncExitStack | None = None


def route_validation(state: SQLAssistantState) -> str:
    """Routes valid SQL forward and invalid SQL through correction retries."""

    if (
        state.validation_result
        and state.validation_result.is_valid
    ):
        return "valid"

    if state.retry_count < 3:
        return "retry"

    return "error"


def route_risk(state: SQLAssistantState) -> str:
    """Routes HIGH-risk SQL to approval and other SQL to execution."""

    if state.risk_level and state.risk_level.value == "HIGH":
        return "high"

    return "execute"


def route_approval(state: SQLAssistantState) -> str:
    """Routes a resumed approval decision to execution or rejection output."""

    if (
        state.approval_decision
        and state.approval_decision.status
        == ApprovalStatus.APPROVED
    ):
        return "approved"

    return "rejected"


def route_execution(state: SQLAssistantState) -> str:
    """Routes successful execution to formatting and failed execution to retry."""

    if (
        state.execution_result
        and state.execution_result.status == "ok"
    ):
        return "ok"

    if state.execution_retry_count < 2:
        return "retry"

    return "done"


def build_graph(checkpointer: AsyncPostgresSaver) -> Any:
    """Builds one graph for both initial execution and approval resume."""

    builder = StateGraph(SQLAssistantState)

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
        {
            "valid": "assess_risk",
            "retry": "generate_sql",
            "error": "handle_error",
        },
    )
    builder.add_conditional_edges(
        "assess_risk",
        route_risk,
        {
            "execute": "execute_query",
            "high": "request_approval",
        },
    )

    builder.add_edge("request_approval", "await_approval")
    builder.add_conditional_edges(
        "await_approval",
        route_approval,
        {
            "approved": "execute_query",
            "rejected": "format_result",
        },
    )

    builder.add_conditional_edges(
        "execute_query",
        route_execution,
        {
            "ok": "format_result",
            "retry": "generate_sql",
            "done": "format_result",
        },
    )
    builder.add_edge("format_result", END)
    builder.add_edge("handle_error", END)

    return builder.compile(checkpointer=checkpointer)


async def init_workflow() -> None:
    """Opens AsyncPostgresSaver and compiles the graph during startup."""

    global _compiled_graph, _workflow_resources

    if _compiled_graph is not None:
        return

    resources = AsyncExitStack()

    try:
        checkpointer = await resources.enter_async_context(
            AsyncPostgresSaver.from_conn_string(
                settings.database_url
            )
        )

        # setup() creates or migrates LangGraph checkpoint tables.
        await checkpointer.setup()

        _compiled_graph = build_graph(checkpointer)
        _workflow_resources = resources
    except Exception:
        await resources.aclose()
        raise


async def close_workflow() -> None:
    """Closes the PostgreSQL checkpointer during application shutdown."""

    global _compiled_graph, _workflow_resources

    _compiled_graph = None

    if _workflow_resources is not None:
        await _workflow_resources.aclose()
        _workflow_resources = None


def get_compiled_graph() -> Any:
    """Returns the initialized graph or fails fast before startup completes."""

    if _compiled_graph is None:
        raise RuntimeError(
            "LangGraph workflow is not initialized"
        )

    return _compiled_graph


def _graph_config(checkpoint_thread_id: str) -> dict[str, Any]:
    """Builds LangGraph configuration for one persistent execution thread."""

    return {
        "configurable": {
            "thread_id": checkpoint_thread_id,
        }
    }


async def run_message_graph(
    session_id: str,
    thread_id: str,
    requester_email: str,
    message: str,
) -> SQLAssistantState:
    """Starts a new graph execution for one user message."""

    graph = get_compiled_graph()
    history = await recent_context(session_id)

    checkpoint_thread_id = (
        f"{session_id}:{thread_id}:{uuid4()}"
    )

    initial_state = SQLAssistantState(
        session_id=session_id,
        thread_id=checkpoint_thread_id,
        requester_email=requester_email,
        messages=history,
        current_question=message,
    )

    result = await graph.ainvoke(
        initial_state,
        config=_graph_config(checkpoint_thread_id),
    )

    return SQLAssistantState.model_validate(result)


async def resume_after_approval(
    approval_id: str,
) -> SQLAssistantState | None:
    """Resumes the exact interrupted checkpoint for an approval request."""

    approval = await get_approval(approval_id)

    if not approval:
        return None

    graph = get_compiled_graph()
    checkpoint_thread_id = approval["thread_id"]
    config = _graph_config(checkpoint_thread_id)

    snapshot = await graph.aget_state(config)

    if not snapshot.values:
        raise RuntimeError(
            "Checkpoint was not found for the approval request"
        )

    checkpoint_state = SQLAssistantState.model_validate(
        snapshot.values
    )

    if checkpoint_state.approval_request_id != approval_id:
        raise RuntimeError(
            "Approval request does not match the saved checkpoint"
        )

    decision = decision_from_row(approval)

    result = await graph.ainvoke(
        Command(
            resume=decision.model_dump(mode="json")
        ),
        config=config,
    )

    return SQLAssistantState.model_validate(result)
