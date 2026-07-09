from app.core.logger_setup import log_event, log_node
from app.models.types import ApprovalStatus, AssistantResponse, RiskLevel, SQLAssistantState
from app.services import audit_service
from app.services.approval_service import create_approval_request
from app.services.executor import execute_readonly_sql
from app.services.llm_service import llm_service
from app.services.risk_assessor import assess_risk
from app.services.session_service import last_successful_sql
from app.services.sql_validation import validate_sql
from app.services.state_store import save_state
from app.graph.state import SQLAssistantStateDict
from app.graph.utils import detect_mutation_keyword


def state_model(state: SQLAssistantStateDict) -> SQLAssistantState:
    return SQLAssistantState.model_validate(state)


async def parse_intent_node(state: SQLAssistantStateDict) -> SQLAssistantStateDict:
    model = state_model(state)
    with log_node(model.session_id, model.thread_id, "parse_intent"):
        if not model.audit_id:
            audit_id = await audit_service.create_audit(
                model.session_id, model.thread_id, model.requester_email, model.current_question
            )
        else:
            audit_id = model.audit_id

        previous_sql = await last_successful_sql(model.session_id)
        try:
            intent = await llm_service.parse_intent(model.current_question, model.messages, previous_sql)
        except Exception as exc:
            await audit_service.update_audit(audit_id, execution_status="error", error_message=str(exc))
            raise

        return {"intent": intent, "audit_id": audit_id, "error": None}


async def generate_sql_node(state: SQLAssistantStateDict) -> SQLAssistantStateDict:
    model = state_model(state)
    with log_node(model.session_id, model.thread_id, "generate_sql"):
        if not model.intent:
            return {"error": "Intent is missing"}

        mutation_keyword = detect_mutation_keyword(model.intent.question, model.current_question)
        if mutation_keyword:
            sql = f"-- refused: request implies a {mutation_keyword} operation\n{mutation_keyword}"
        else:
            sql = await llm_service.generate_sql(
                model.intent, previous_error=model.error, previous_sql=model.generated_sql
            )
        if model.audit_id:
            await audit_service.update_audit(model.audit_id, generated_sql=sql)
        return {"generated_sql": sql, "error": None}


async def validate_sql_node(state: SQLAssistantStateDict) -> SQLAssistantStateDict:
    model = state_model(state)
    with log_node(model.session_id, model.thread_id, "validate_sql"):
        if not model.generated_sql:
            return {"error": "No SQL generated", "retry_count": model.retry_count + 1}
        result = validate_sql(model.generated_sql)
        if not result.is_valid:
            error = "; ".join(result.errors)
            log_event(
                "sql.validation.failed",
                session_id=model.session_id,
                thread_id=model.thread_id,
                attempt_number=model.retry_count + 1,
                previous_error=error,
                corrected_sql=None,
            )
            if model.audit_id:
                await audit_service.update_audit(model.audit_id, execution_status="blocked", error_message=error)
            return {"validation_result": result, "error": error, "retry_count": model.retry_count + 1}
        return {"validation_result": result, "error": None}


async def assess_risk_node(state: SQLAssistantStateDict) -> SQLAssistantStateDict:
    model = state_model(state)
    with log_node(model.session_id, model.thread_id, "assess_risk"):
        if not model.generated_sql or not model.validation_result:
            return {"risk_level": RiskLevel.HIGH, "risk_justification": "Missing SQL or validation result."}
        risk, justification = assess_risk(model.generated_sql, model.validation_result)
        if model.audit_id:
            await audit_service.update_audit(model.audit_id, risk_level=risk.value)
        return {"risk_level": risk, "risk_justification": justification}


async def request_approval_node(state: SQLAssistantStateDict) -> SQLAssistantStateDict:
    model = state_model(state)
    with log_node(model.session_id, model.thread_id, "request_approval"):
        approval_id = await create_approval_request(
            session_id=model.session_id,
            thread_id=model.thread_id,
            requester_email=model.requester_email,
            question=model.current_question,
            generated_sql=model.generated_sql or "",
            risk_level=model.risk_level or RiskLevel.HIGH,
            risk_justification=model.risk_justification or "High-risk query requires approval.",
        )
        response = AssistantResponse(
            message="This query requires review before execution. You will be notified when it is approved.",
            sql=model.generated_sql,
            risk_level=model.risk_level,
            risk_justification=model.risk_justification,
            assumptions=model.intent.assumptions if model.intent else [],
            pending_approval=True,
            approval_request_id=approval_id,
            audit_id=model.audit_id,
        )
        if model.audit_id:
            await audit_service.update_audit(
                audit_id=model.audit_id, approval_request_id=approval_id, execution_status="pending"
            )
        new_state = model.model_copy(update={"approval_request_id": approval_id, "final_response": response})
        await save_state(new_state)
        return {"approval_request_id": approval_id, "final_response": response}


async def await_approval_node(state: SQLAssistantStateDict) -> SQLAssistantStateDict:
    model = state_model(state)
    with log_node(model.session_id, model.thread_id, "await_approval"):
        decision = model.approval_decision
        if not decision:
            return {}
        if decision.status == ApprovalStatus.APPROVED:
            final_sql = decision.modified_sql or model.generated_sql
            return {"approved_sql": final_sql, "error": None, "final_response": None}
        if decision.status in {ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED}:
            reason = decision.rejection_reason or "The query was not approved."
            response = AssistantResponse(
                message=f"The query was not executed: {reason}",
                sql=model.generated_sql,
                risk_level=model.risk_level,
                risk_justification=model.risk_justification,
                pending_approval=False,
                approval_request_id=model.approval_request_id,
                rejection_reason=reason,
                audit_id=model.audit_id,
                execution_status="rejected",
            )
            if model.audit_id:
                await audit_service.update_audit(model.audit_id, execution_status="rejected", error_message=reason)
            return {"final_response": response, "error": reason}
        return {}


async def execute_query_node(state: SQLAssistantStateDict) -> SQLAssistantStateDict:
    model = state_model(state)
    with log_node(model.session_id, model.thread_id, "execute_query"):
        sql = model.approved_sql or model.generated_sql
        if not sql:
            return {"error": "No SQL available for execution"}

        validation = validate_sql(sql)
        if not validation.is_valid:
            error = "; ".join(validation.errors)
            if model.audit_id:
                await audit_service.update_audit(model.audit_id, execution_status="blocked", error_message=error)
            return {"validation_result": validation, "error": error}

        result = await execute_readonly_sql(sql, model.session_id, model.thread_id)
        updates: SQLAssistantStateDict = {"execution_result": result}
        if result.status != "ok":
            updates["error"] = result.error_message or result.status
            updates["execution_retry_count"] = model.execution_retry_count + 1
            if model.audit_id:
                await audit_service.update_audit(
                    model.audit_id,
                    final_sql=sql,
                    execution_status=result.status,
                    execution_duration_ms=result.duration_ms,
                    row_count=result.row_count,
                    error_message=result.error_message,
                )
            return updates

        summary = f"Returned {result.row_count} row(s)" + ("; result truncated." if result.truncated else ".")
        if model.audit_id:
            await audit_service.update_audit(
                model.audit_id,
                final_sql=sql,
                execution_status="ok",
                execution_duration_ms=result.duration_ms,
                row_count=result.row_count,
                result_summary=summary,
            )
        updates["error"] = None
        return updates


async def format_result_node(state: SQLAssistantStateDict) -> SQLAssistantStateDict:
    model = state_model(state)
    with log_node(model.session_id, model.thread_id, "format_result"):
        if model.final_response and model.final_response.rejection_reason:
            await save_state(model)
            return {}

        risk_warning = (
            "Warning: this query was classified as MEDIUM risk (bounded but potentially slow or broad). "
            if model.risk_level == RiskLevel.MEDIUM
            else ""
        )

        was_modified = bool(model.approved_sql and model.generated_sql and model.approved_sql != model.generated_sql)
        original_sql = model.generated_sql if was_modified else None
        modification_note = "The approver modified this query before running it. " if was_modified else ""

        if model.execution_result and model.execution_result.status == "ok":
            trunc = " Results were truncated to the configured maximum." if model.execution_result.truncated else ""
            message = (
                f"{risk_warning}{modification_note}Query executed successfully. "
                f"Returned {model.execution_result.row_count} row(s).{trunc}"
            )
            response = AssistantResponse(
                message=message,
                sql=model.approved_sql or model.generated_sql,
                original_sql=original_sql,
                risk_level=model.risk_level,
                risk_justification=model.risk_justification,
                assumptions=model.intent.assumptions if model.intent else [],
                columns=model.execution_result.columns,
                rows=model.execution_result.rows,
                truncated=model.execution_result.truncated,
                pending_approval=False,
                approval_request_id=model.approval_request_id,
                audit_id=model.audit_id,
                execution_status="ok",
            )
            new_state = model.model_copy(update={"final_response": response})
            await save_state(new_state)
            return {"final_response": response}

        error = model.error or (model.execution_result.error_message if model.execution_result else "Unknown failure")
        response = AssistantResponse(
            message=f"{risk_warning}{modification_note}I could not execute the query: {error}",
            sql=model.approved_sql or model.generated_sql,
            original_sql=original_sql,
            risk_level=model.risk_level,
            risk_justification=model.risk_justification,
            assumptions=model.intent.assumptions if model.intent else [],
            pending_approval=False,
            approval_request_id=model.approval_request_id,
            audit_id=model.audit_id,
            execution_status=model.execution_result.status if model.execution_result else "blocked",
        )
        new_state = model.model_copy(update={"final_response": response})
        await save_state(new_state)
        return {"final_response": response}


async def handle_error_node(state: SQLAssistantStateDict) -> SQLAssistantStateDict:
    model = state_model(state)
    with log_node(model.session_id, model.thread_id, "handle_error"):
        error = model.error or "Unknown error"
        response = AssistantResponse(
            message=f"I could not produce a safe SQL query: {error}",
            sql=model.generated_sql,
            risk_level=model.risk_level,
            risk_justification=model.risk_justification,
            assumptions=model.intent.assumptions if model.intent else [],
            audit_id=model.audit_id,
            execution_status="blocked",
        )
        if model.audit_id:
            await audit_service.update_audit(model.audit_id, execution_status="blocked", error_message=error)
        new_state = model.model_copy(update={"final_response": response})
        await save_state(new_state)
        return {"final_response": response}
