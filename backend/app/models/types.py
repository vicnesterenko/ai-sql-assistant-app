from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Intent(BaseModel):
    question: str = Field(
        description="Resolved natural-language analytics question after considering conversation context."
    )
    is_follow_up: bool = Field(
        default=False, description="True when the current user message depends on previous SQL or previous question."
    )
    assumptions: list[str] = Field(
        default_factory=list, description="Reasonable defaults made for ambiguous user input and surfaced to the user."
    )
    referenced_previous_sql: str | None = Field(
        default=None, description="Previous SQL used to resolve this follow-up, if any."
    )


class ValidationResult(BaseModel):
    is_valid: bool = Field(description="Whether the generated SQL passed static validation and is safe to continue.")
    errors: list[str] = Field(
        default_factory=list, description="Validation errors that must be fixed before execution or approval."
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-blocking validation warnings, for example missing WHERE on large table."
    )
    referenced_tables: list[str] = Field(default_factory=list, description="Tables referenced by the SQL statement.")
    referenced_columns: list[str] = Field(
        default_factory=list, description="Columns referenced by the SQL statement in table.column or column format."
    )
    normalized_sql: str | None = Field(default=None, description="Parser-normalized SQL when available.")


class ApprovalDecision(BaseModel):
    status: ApprovalStatus = Field(description="Approver decision status.")
    approver_email: str | None = Field(
        default=None, description="Email of the human approver who resolved the request."
    )
    modified_sql: str | None = Field(
        default=None, description="Approver-edited SQL. If omitted, the generated SQL is approved as-is."
    )
    rejection_reason: str | None = Field(default=None, description="Required reason when the query is rejected.")


class ExecutionResult(BaseModel):
    status: Literal["ok", "error", "timeout"] = Field(description="Execution outcome status.")
    columns: list[str] = Field(default_factory=list, description="Column names returned by the final SELECT query.")
    rows: list[dict[str, Any]] = Field(
        default_factory=list, description="Truncated row payload returned to UI. Not stored in LLM memory."
    )
    row_count: int = Field(default=0, description="Number of rows returned after truncation.")
    truncated: bool = Field(
        default=False, description="True when MAX_RESULT_ROWS was exceeded and response rows were truncated."
    )
    duration_ms: int = Field(default=0, description="Actual database execution duration in milliseconds.")
    error_message: str | None = Field(
        default=None, description="Database error or timeout message, if execution failed."
    )


class AssistantResponse(BaseModel):
    message: str = Field(description="User-facing natural language response.")
    sql: str | None = Field(default=None, description="Generated or approved SQL shown in the UI collapsible block.")
    risk_level: RiskLevel | None = Field(default=None, description="Risk badge shown to the user.")
    risk_justification: str | None = Field(default=None, description="Tooltip text explaining the risk classification.")
    assumptions: list[str] = Field(default_factory=list, description="Assumptions surfaced to the user.")
    columns: list[str] = Field(default_factory=list, description="Result table column names.")
    rows: list[dict[str, Any]] = Field(default_factory=list, description="Result rows for the current turn only.")
    truncated: bool = Field(default=False, description="Whether the result table was truncated.")
    pending_approval: bool = Field(default=False, description="True when query is suspended for human review.")
    approval_request_id: str | None = Field(default=None, description="Approval queue identifier used by polling UI.")
    rejection_reason: str | None = Field(default=None, description="Human rejection reason when relevant.")
    audit_id: str | None = Field(default=None, description="Audit row identifier for traceability.")


class SQLAssistantState(BaseModel):
    session_id: str = Field(description="Conversation session identifier.")
    thread_id: str = Field(description="LangGraph thread identifier for checkpointing/resumability.")
    requester_email: str = Field(description="Email of the user who asked the question.")
    messages: list[dict[str, str]] = Field(
        default_factory=list, description="Conversation message history containing roles and sanitized content."
    )
    current_question: str = Field(description="Current raw user message.")
    intent: Intent | None = Field(default=None, description="Structured intent produced by parse_intent.")
    generated_sql: str | None = Field(default=None, description="LLM-proposed SQL before validation and approval.")
    validation_result: ValidationResult | None = Field(default=None, description="Static SQL validation output.")
    risk_level: RiskLevel | None = Field(default=None, description="Risk classification for the validated SQL.")
    risk_justification: str | None = Field(default=None, description="Human-readable risk rationale.")
    approval_request_id: str | None = Field(default=None, description="Approval queue ID for high-risk queries.")
    approval_decision: ApprovalDecision | None = Field(
        default=None, description="Human approval decision when graph resumes."
    )
    approved_sql: str | None = Field(
        default=None, description="Final SQL after approval, possibly modified by approver."
    )
    execution_result: ExecutionResult | None = Field(default=None, description="Database execution output.")
    retry_count: int = Field(default=0, description="Validation or execution retry counter.")
    execution_retry_count: int = Field(default=0, description="Execution correction retry counter.")
    error: str | None = Field(default=None, description="Current error to be handled by handle_error.")
    final_response: AssistantResponse | None = Field(
        default=None, description="Final API response returned to frontend."
    )
    audit_id: str | None = Field(default=None, description="Audit row ID for this attempt.")


class CreateSessionRequest(BaseModel):
    requester_email: str


class SessionResponse(BaseModel):
    session_id: str
    created_at: str


class ChatMessageRequest(BaseModel):
    message: str
    thread_id: str = "default"


class MessageRecord(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str
    response: AssistantResponse | None = None


class ApprovalItem(BaseModel):
    id: str
    session_id: str
    thread_id: str
    requester_email: str
    original_question: str
    generated_sql: str
    risk_level: str
    risk_justification: str
    status: str
    approver_email: str | None = None
    approved_sql: str | None = None
    rejection_reason: str | None = None
    created_at: str
    resolved_at: str | None = None


class ApprovalListResponse(BaseModel):
    items: list[ApprovalItem]
    total: int


class ApproveRequest(BaseModel):
    modified_sql: str | None = None


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1)


class AuditEntry(BaseModel):
    id: str
    session_id: str
    thread_id: str
    requester_email: str
    question: str
    generated_sql: str | None = None
    final_sql: str | None = None
    risk_level: str | None = None
    approval_request_id: str | None = None
    execution_status: str | None = None
    execution_duration_ms: int | None = None
    row_count: int | None = None
    error_message: str | None = None
    result_summary: str | None = None
    created_at: str


class AuditListResponse(BaseModel):
    items: list[AuditEntry]
    total: int


class ColumnSchema(BaseModel):
    name: str
    data_type: str
    nullable: bool
    description: str | None = None


class TableSchema(BaseModel):
    name: str
    description: str
    large: bool = False
    sensitive: bool = False
    columns: list[ColumnSchema]


class SchemaResponse(BaseModel):
    tables: list[TableSchema]


class HealthResponse(BaseModel):
    status: str
    message: str
    db_connected: bool
    sample_query_latency_ms: int | None = None
