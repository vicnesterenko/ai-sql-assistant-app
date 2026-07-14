"""Pydantic-схема стану LangGraph для AI SQL Assistant."""

from pydantic import BaseModel, Field

from app.models.types import (
    ApprovalDecision,
    AssistantResponse,
    ExecutionResult,
    Intent,
    RiskLevel,
    ValidationResult,
)


class SQLAssistantState(BaseModel):
    """Повний стан workflow для генерації та виконання SQL."""

    session_id: str = Field(
        description="Conversation session identifier."
    )
    thread_id: str = Field(
        description="LangGraph thread identifier for checkpointing."
    )
    requester_email: str = Field(
        description="Email of the user who asked the question."
    )
    messages: list[dict[str, str]] = Field(
        default_factory=list,
        description="Sanitized conversation history.",
    )
    current_question: str = Field(
        description="Current raw user message."
    )
    intent: Intent | None = Field(
        default=None,
        description="Structured intent produced by parse_intent.",
    )
    generated_sql: str | None = Field(
        default=None,
        description="LLM-proposed SQL before validation.",
    )
    validation_result: ValidationResult | None = Field(
        default=None,
        description="Static SQL validation output.",
    )
    risk_level: RiskLevel | None = Field(
        default=None,
        description="Risk classification for the validated SQL.",
    )
    risk_justification: str | None = Field(
        default=None,
        description="Human-readable risk rationale.",
    )
    approval_request_id: str | None = Field(
        default=None,
        description="Approval queue identifier.",
    )
    approval_decision: ApprovalDecision | None = Field(
        default=None,
        description="Human approval decision after resume.",
    )
    approved_sql: str | None = Field(
        default=None,
        description="Final SQL approved by a human.",
    )
    execution_result: ExecutionResult | None = Field(
        default=None,
        description="Database execution output.",
    )
    retry_count: int = Field(
        default=0,
        ge=0,
        description="SQL generation and validation retry counter.",
    )
    execution_retry_count: int = Field(
        default=0,
        ge=0,
        description="SQL execution retry counter.",
    )
    error: str | None = Field(
        default=None,
        description="Current workflow error.",
    )
    final_response: AssistantResponse | None = Field(
        default=None,
        description="Final API response returned to the frontend.",
    )
    audit_id: str | None = Field(
        default=None,
        description="Audit row identifier for the current attempt.",
    )
