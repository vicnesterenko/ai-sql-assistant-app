"""Вузли LangGraph для генерації, перевірки, погодження та виконання SQL."""

from typing import Any

from app.core.logger_setup import log_event, log_node
from app.graph.state import SQLAssistantState
from app.models.types import ApprovalDecision, ApprovalStatus, AssistantResponse, RiskLevel
from app.services import audit_service
from app.services.approval_service import create_approval_request
from app.services.executor import execute_readonly_sql
from app.services.llm_service import llm_service
from app.services.risk_assessor import assess_risk
from app.services.session_service import last_successful_sql
from app.services.sql_validation import validate_sql
from app.services.state_store import save_state


StateUpdate = dict[str, Any]


async def parse_intent_node(state: SQLAssistantState) -> StateUpdate:
    """Створює audit-запис і визначає намір користувача."""

    with log_node(state.session_id, state.thread_id, "parse_intent"):
        if not state.audit_id:
            audit_id = await audit_service.create_audit(
                state.session_id,
                state.thread_id,
                state.requester_email,
                state.current_question,
            )
        else:
            audit_id = state.audit_id

        previous_sql = await last_successful_sql(state.session_id)

        try:
            intent = await llm_service.parse_intent(
                state.current_question,
                state.messages,
                previous_sql,
            )
        except Exception as exc:
            await audit_service.update_audit(
                audit_id,
                execution_status="error",
                error_message=str(exc),
            )
            raise

        return {
            "intent": intent,
            "audit_id": audit_id,
            "error": None,
        }


async def generate_sql_node(
    state: SQLAssistantState,
) -> StateUpdate:
    """Генерує read-only SQL і обробляє помилки LLM."""

    with log_node(
        state.session_id,
        state.thread_id,
        "generate_sql",
    ):
        if not state.intent:
            return {
                "generated_sql": None,
                "error": "Intent is missing",
            }

        try:
            sql = await llm_service.generate_sql(
                state.intent,
                previous_error=state.error,
                previous_sql=state.generated_sql,
            )
        except Exception as exc:
            error = f"SQL generation failed: {exc}"

            log_event(
                "sql.generation.failed",
                session_id=state.session_id,
                thread_id=state.thread_id,
                error=str(exc),
            )

            if state.audit_id:
                await audit_service.update_audit(
                    state.audit_id,
                    execution_status="error",
                    error_message=error,
                )

            return {
                "generated_sql": None,
                "error": error,
            }

        if state.audit_id:
            await audit_service.update_audit(
                state.audit_id,
                generated_sql=sql,
            )

        return {
            "generated_sql": sql,
            "error": None,
        }


async def validate_sql_node(state: SQLAssistantState) -> StateUpdate:
    """Перевіряє SQL і зберігає причини його блокування."""

    with log_node(state.session_id, state.thread_id, "validate_sql"):
        if not state.generated_sql:
            return {
                "error": "No SQL generated",
                "retry_count": state.retry_count + 1,
            }

        result = validate_sql(state.generated_sql)

        if not result.is_valid:
            error = "; ".join(result.errors)

            log_event(
                "sql.validation.failed",
                session_id=state.session_id,
                thread_id=state.thread_id,
                attempt_number=state.retry_count + 1,
                previous_error=error,
                corrected_sql=None,
            )

            if state.audit_id:
                await audit_service.update_audit(
                    state.audit_id,
                    execution_status="blocked",
                    error_message=error,
                )

            return {
                "validation_result": result,
                "error": error,
                "retry_count": state.retry_count + 1,
            }

        return {
            "validation_result": result,
            "error": None,
        }


async def assess_risk_node(state: SQLAssistantState) -> StateUpdate:
    """Оцінює ризик SQL і формує пояснення рівня ризику."""

    with log_node(state.session_id, state.thread_id, "assess_risk"):
        if not state.generated_sql or not state.validation_result:
            return {
                "risk_level": RiskLevel.HIGH,
                "risk_justification": (
                    "Missing SQL or validation result."
                ),
            }

        risk, justification = assess_risk(
            state.generated_sql,
            state.validation_result,
        )

        if state.audit_id:
            await audit_service.update_audit(
                state.audit_id,
                risk_level=risk.value,
            )

        return {
            "risk_level": risk,
            "risk_justification": justification,
        }


async def request_approval_node(
    state: SQLAssistantState,
) -> StateUpdate:
    """Створює approval-запит і зберігає призупинений state."""

    with log_node(
        state.session_id,
        state.thread_id,
        "request_approval",
    ):
        approval_id = await create_approval_request(
            session_id=state.session_id,
            thread_id=state.thread_id,
            requester_email=state.requester_email,
            question=state.current_question,
            generated_sql=state.generated_sql or "",
            risk_level=state.risk_level or RiskLevel.HIGH,
            risk_justification=(
                state.risk_justification
                or "High-risk query requires approval."
            ),
        )

        response = AssistantResponse(
            message=(
                "This query requires review before execution. "
                "You will be notified when it is approved."
            ),
            sql=state.generated_sql,
            risk_level=state.risk_level,
            risk_justification=state.risk_justification,
            assumptions=(
                state.intent.assumptions
                if state.intent
                else []
            ),
            pending_approval=True,
            approval_request_id=approval_id,
            audit_id=state.audit_id,
        )

        if state.audit_id:
            await audit_service.update_audit(
                audit_id=state.audit_id,
                approval_request_id=approval_id,
                execution_status="pending",
            )

        new_state = state.model_copy(
            update={
                "approval_request_id": approval_id,
                "final_response": response,
            }
        )
        await save_state(new_state)

        return {
            "approval_request_id": approval_id,
            "final_response": response,
        }


async def await_approval_node(
    state: SQLAssistantState,
) -> StateUpdate:
    """Призупиняє HIGH-risk запит і обробляє рішення approver."""

    with log_node(
        state.session_id,
        state.thread_id,
        "await_approval",
    ):
        decision_payload = interrupt(
            {
                "type": "sql_approval",
                "approval_request_id": state.approval_request_id,
                "sql": state.generated_sql,
                "risk_level": (
                    state.risk_level.value
                    if state.risk_level
                    else RiskLevel.HIGH.value
                ),
                "risk_justification": state.risk_justification,
            }
        )

        decision = ApprovalDecision.model_validate(
            decision_payload
        )

        if decision.status == ApprovalStatus.APPROVED:
            final_sql = (
                decision.modified_sql
                or state.generated_sql
            )

            if not final_sql:
                return {
                    "approval_decision": decision,
                    "approved_sql": None,
                    "error": "Approved SQL is missing.",
                    "final_response": None,
                }

            return {
                "approval_decision": decision,
                "approved_sql": final_sql,
                "error": None,
                "final_response": None,
            }

        reason = (
            decision.rejection_reason
            or "The query was not approved."
        )

        response = AssistantResponse(
            message=f"The query was not executed: {reason}",
            sql=state.generated_sql,
            risk_level=state.risk_level,
            risk_justification=state.risk_justification,
            pending_approval=False,
            approval_request_id=state.approval_request_id,
            rejection_reason=reason,
            audit_id=state.audit_id,
            execution_status=decision.status.value,
        )

        if state.audit_id:
            await audit_service.update_audit(
                state.audit_id,
                execution_status=decision.status.value,
                error_message=reason,
            )

        return {
            "approval_decision": decision,
            "final_response": response,
            "error": reason,
        }


async def execute_query_node(
    state: SQLAssistantState,
) -> StateUpdate:
    """Повторно перевіряє та виконує дозволений SQL."""

    with log_node(
        state.session_id,
        state.thread_id,
        "execute_query",
    ):
        sql = state.approved_sql or state.generated_sql

        if not sql:
            return {
                "error": "No SQL available for execution"
            }

        validation = validate_sql(sql)

        if not validation.is_valid:
            error = "; ".join(validation.errors)

            if state.audit_id:
                await audit_service.update_audit(
                    state.audit_id,
                    execution_status="blocked",
                    error_message=error,
                )

            return {
                "validation_result": validation,
                "error": error,
            }

        result = await execute_readonly_sql(
            sql,
            state.session_id,
            state.thread_id,
        )

        updates: StateUpdate = {
            "execution_result": result,
        }

        if result.status != "ok":
            updates["error"] = (
                result.error_message
                or result.status
            )
            updates["execution_retry_count"] = (
                state.execution_retry_count + 1
            )

            if state.audit_id:
                await audit_service.update_audit(
                    state.audit_id,
                    final_sql=sql,
                    execution_status=result.status,
                    execution_duration_ms=result.duration_ms,
                    row_count=result.row_count,
                    error_message=result.error_message,
                )

            return updates

        summary = (
            f"Returned {result.row_count} row(s)"
            + (
                "; result truncated."
                if result.truncated
                else "."
            )
        )

        if state.audit_id:
            await audit_service.update_audit(
                state.audit_id,
                final_sql=sql,
                execution_status="ok",
                execution_duration_ms=result.duration_ms,
                row_count=result.row_count,
                result_summary=summary,
            )

        updates["error"] = None
        return updates


async def format_result_node(
    state: SQLAssistantState,
) -> StateUpdate:
    """Формує фінальну відповідь із результатом або помилкою."""

    with log_node(
        state.session_id,
        state.thread_id,
        "format_result",
    ):
        if (
            state.final_response
            and state.final_response.rejection_reason
        ):
            await save_state(state)
            return {}

        risk_warning = (
            "Warning: this query was classified as MEDIUM risk "
            "(bounded but potentially slow or broad). "
            if state.risk_level == RiskLevel.MEDIUM
            else ""
        )

        was_modified = bool(
            state.approved_sql
            and state.generated_sql
            and state.approved_sql != state.generated_sql
        )
        original_sql = (
            state.generated_sql
            if was_modified
            else None
        )
        modification_note = (
            "The approver modified this query before running it. "
            if was_modified
            else ""
        )

        if (
            state.execution_result
            and state.execution_result.status == "ok"
        ):
            truncation_note = (
                " Results were truncated to the configured maximum."
                if state.execution_result.truncated
                else ""
            )
            message = (
                f"{risk_warning}{modification_note}"
                "Query executed successfully. "
                f"Returned {state.execution_result.row_count} "
                f"row(s).{truncation_note}"
            )

            response = AssistantResponse(
                message=message,
                sql=(
                    state.approved_sql
                    or state.generated_sql
                ),
                original_sql=original_sql,
                risk_level=state.risk_level,
                risk_justification=state.risk_justification,
                assumptions=(
                    state.intent.assumptions
                    if state.intent
                    else []
                ),
                columns=state.execution_result.columns,
                rows=state.execution_result.rows,
                truncated=state.execution_result.truncated,
                pending_approval=False,
                approval_request_id=state.approval_request_id,
                audit_id=state.audit_id,
                execution_status="ok",
            )

            new_state = state.model_copy(
                update={"final_response": response}
            )
            await save_state(new_state)

            return {"final_response": response}

        error = (
            state.error
            or (
                state.execution_result.error_message
                if state.execution_result
                else "Unknown failure"
            )
        )

        response = AssistantResponse(
            message=(
                f"{risk_warning}{modification_note}"
                f"I could not execute the query: {error}"
            ),
            sql=state.approved_sql or state.generated_sql,
            original_sql=original_sql,
            risk_level=state.risk_level,
            risk_justification=state.risk_justification,
            assumptions=(
                state.intent.assumptions
                if state.intent
                else []
            ),
            pending_approval=False,
            approval_request_id=state.approval_request_id,
            audit_id=state.audit_id,
            execution_status=(
                state.execution_result.status
                if state.execution_result
                else "blocked"
            ),
        )

        new_state = state.model_copy(
            update={"final_response": response}
        )
        await save_state(new_state)

        return {"final_response": response}


async def handle_error_node(
    state: SQLAssistantState,
) -> StateUpdate:
    """Формує безпечну відповідь після невиправної помилки."""

    with log_node(
        state.session_id,
        state.thread_id,
        "handle_error",
    ):
        error = state.error or "Unknown error"

        response = AssistantResponse(
            message=(
                "I could not produce a safe SQL query: "
                f"{error}"
            ),
            sql=state.generated_sql,
            risk_level=state.risk_level,
            risk_justification=state.risk_justification,
            assumptions=(
                state.intent.assumptions
                if state.intent
                else []
            ),
            audit_id=state.audit_id,
            execution_status="blocked",
        )

        if state.audit_id:
            await audit_service.update_audit(
                state.audit_id,
                execution_status="blocked",
                error_message=error,
            )

        new_state = state.model_copy(
            update={"final_response": response}
        )
        await save_state(new_state)

        return {"final_response": response}

def route_approval(
    state: SQLAssistantState,
) -> str:
    """Маршрутизує отримане рішення approver."""

    if not state.approval_decision:
        raise RuntimeError(
            "Approval node completed without an approval decision."
        )

    if (
        state.approval_decision.status
        == ApprovalStatus.APPROVED
    ):
        return "approved"

    return "rejected"