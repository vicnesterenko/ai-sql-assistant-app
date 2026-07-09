from typing_extensions import TypedDict

from app.models.types import (
    ApprovalDecision,
    AssistantResponse,
    ExecutionResult,
    Intent,
    RiskLevel,
    ValidationResult,
)


class SQLAssistantStateDict(TypedDict, total=False):
    session_id: str
    thread_id: str
    requester_email: str
    messages: list[dict[str, str]]
    current_question: str
    intent: Intent | None
    generated_sql: str | None
    validation_result: ValidationResult | None
    risk_level: RiskLevel | None
    risk_justification: str | None
    approval_request_id: str | None
    approval_decision: ApprovalDecision | None
    approved_sql: str | None
    execution_result: ExecutionResult | None
    retry_count: int
    execution_retry_count: int
    error: str | None
    final_response: AssistantResponse | None
    audit_id: str | None
