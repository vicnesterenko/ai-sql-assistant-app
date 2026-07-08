# Technical Assessment: AI SQL Assistant
 
**Stack:** Python · FastAPI · LangGraph · LangChain · React · PostgreSQL

**Submission:** Git repository (private GitHub or GitLab) + short README with run instructions

---

## 1. Context

Your company's data team receives dozens of ad-hoc analytics requests per week from product managers, finance analysts, and operations staff. Most of these are variations of "how many users did X last month" or "give me a breakdown of Y by region." Today, the flow is:

1. Analyst writes a Slack message.
2. Data engineer receives it, writes SQL, pastes result into a Google Sheet.
3. Repeat next week.

The goal is to replace step 1–2 with an internal chat interface where non-technical staff can ask questions in plain language, get SQL generated and validated automatically, see the results in a readable format, and - critically - have a human engineer review and approve queries that touch sensitive or expensive operations before execution.

This is **not** a public-facing product. It is an internal tool used by ~20 people. Reliability and safety matter more than UI polish.

---

## 2. Business Requirements

| ID | Requirement |
|----|-------------|
| BR-1 | A user can type a question in natural language and receive a SQL query + results. |
| BR-2 | The system must refuse or flag queries that could mutate data. |
| BR-3 | Queries estimated to be expensive (large scans, no index hints, unbounded ranges) must be routed to a designated approver before execution. |
| BR-4 | An approver can approve, reject, or modify the SQL before it runs. |
| BR-5 | Conversation context is preserved within a session so follow-up questions work naturally ("now group that by region", "exclude last month"). |
| BR-6 | Results must be paginated and exportable to CSV. |
| BR-7 | Every query attempt - generated SQL, risk level, execution outcome, approver decision - must be auditable. |

---

## 3. Sample User Interactions

The following represent real-world inputs the system must handle gracefully. Your implementation will be tested against these and similar inputs.

```
"How many new users signed up in April 2025, broken down by acquisition channel?"

"Show me the top 20 merchants by transaction volume last quarter, excluding internal test accounts."

"What's the average loan approval time for applications submitted in Q1?"

"Delete all test users from the database."  ← must be blocked

"Give me everything from the users table."  ← must trigger risk flow

"Actually, filter that by users who signed up after January 1st."  ← follow-up, uses previous context

"Run the same query but for Q4 2024."  ← context-aware continuation
```

---

## 4. Functional Requirements

### 4.1 SQL Generation

- Accept a natural-language question and produce a syntactically valid SQL `SELECT` statement targeting a provided schema.
- The system must use the schema context (table names, column names, types, relationships) when generating SQL - not hallucinate table names.
- Generated SQL must include a comment block identifying which tables were used and why.
- If the question is ambiguous (e.g., "show me users" - which columns? which limit?), the system must make a reasonable default decision **and surface that decision to the user** in the response ("I assumed you wanted the last 100 rows ordered by signup date - let me know if you meant something else").

### 4.2 SQL Validation

Before any SQL is executed or sent for approval, the system must perform static validation:

- **Syntax check** - the SQL must be parseable (use `sqlglot` or equivalent).
- **Schema compliance** - all referenced tables and columns must exist in the provided schema.
- **Forbidden operations** - any statement containing `INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `ALTER`, `GRANT`, `REVOKE`, `EXEC`, or `CALL` must be rejected immediately with a user-facing explanation.
- **Structural limits** - queries missing a `WHERE` clause on large tables (configurable list) must be flagged.
- If validation fails, the system must attempt to correct the SQL automatically (up to **2 retries**) before surfacing an error to the user.

### 4.3 Risk Assessment

Each validated query must be assigned a risk level:

| Level | Criteria | Action |
|-------|----------|--------|
| `LOW` | Narrow scope, indexed columns, explicit `LIMIT`, no sensitive tables | Execute immediately |
| `MEDIUM` | Moderate scope, possibly slow but bounded | Warn user, execute after acknowledgment |
| `HIGH` | Full table scan, sensitive tables (configurable), unbounded result set, or contains subqueries across multiple large tables | Block execution, route to approval queue |

Risk level determination is a judgment call - document your heuristics clearly. There is no single correct answer.

### 4.4 Human Approval Flow

When a query is `HIGH` risk:

1. The query is saved to an **approval queue** with status `PENDING_REVIEW`.
2. The user sees a holding message: "This query requires review before execution. You'll be notified when it's approved."
3. An approver (a user with the `approver` role) sees the pending query in a dedicated UI panel.
4. The approver can:
   - **Approve** - the original SQL runs as-is.
   - **Approve with modification** - the approver edits the SQL, then approves. The modified SQL runs and the diff is shown to the original requester.
   - **Reject** - with a required reason string. The requester sees the rejection reason.
5. On approval/rejection, the requester's session must resume automatically (polling or WebSocket - your choice, document the trade-off).

**What happens if the approver never responds?** Define a timeout policy and implement it.

### 4.5 Query Execution

- Execute approved/low-risk SQL against a real PostgreSQL instance (provided via `DATABASE_URL`).
- Hard limits (configurable via env):
  - `QUERY_TIMEOUT_SECONDS` - default `30`
  - `MAX_RESULT_ROWS` - default `1000`
- If the query returns more than `MAX_RESULT_ROWS`, truncate and inform the user.
- If execution exceeds `QUERY_TIMEOUT_SECONDS`, cancel the query and return a timeout error.
- Execution errors must be fed back into the graph for a retry attempt (up to 1 retry with a corrected query).

### 4.6 Conversational Memory

- Within a session (defined as a `session_id`), the system must maintain context across turns.
- A follow-up question must be able to reference the previous query implicitly ("now group by region", "exclude the top 5", "show me the same for last year").
- Context is conversation-scoped, not user-scoped. Starting a new session starts fresh.
- The system must **not** carry forward sensitive data (raw query results) into the context window - only the question, generated SQL, and summary of results.

---

## 5. LangGraph Workflow

You must implement the orchestration logic as a `StateGraph`. The following nodes and edges are required. You may add intermediate nodes but may not remove or merge the required ones.

### 5.1 Required Nodes

| Node | Responsibility |
|------|---------------|
| `parse_intent` | Resolves the current user message in the context of conversation history. Produces a structured `Intent` object. |
| `generate_sql` | Converts the `Intent` + schema into a candidate SQL string. |
| `validate_sql` | Runs static validation (syntax, schema, forbidden ops). Produces `ValidationResult`. |
| `assess_risk` | Classifies the validated query. Produces `RiskLevel` + justification. |
| `request_approval` | Persists the query to the approval queue, emits a user-facing waiting message, suspends graph. |
| `await_approval` | Resumes after human decision. Routes based on `ApprovalDecision`. |
| `execute_query` | Runs the SQL, enforces limits, captures timing. |
| `format_result` | Shapes execution output into the response schema. |
| `handle_error` | Central error handler - routes to retry, reformulation, or final failure. |

### 5.2 Required Edges and Conditions

```
parse_intent
    │
    ▼
generate_sql
    │
    ▼
validate_sql ──(invalid, attempt < 2)──► generate_sql   [retry loop]
    │
  (valid)
    │
    ▼
assess_risk
    │
    ├──(LOW)──────────────────────────────────► execute_query
    │
    ├──(MEDIUM)── [emit warning to user] ──────► execute_query
    │
    └──(HIGH)────────────────────────────────► request_approval
                                                    │
                                               await_approval
                                                    │
                                         ┌──────────┴──────────┐
                                      (approved)           (rejected)
                                         │                     │
                                    execute_query         format_result
                                         │                 (rejection msg)
                                         ▼
                                    execute_query ──(SQL error, attempt < 1)──► generate_sql
                                         │
                                       (ok)
                                         │
                                    format_result
```

### 5.3 Resumability

The graph must be **persistable and resumable**. When a session is waiting for human approval, the graph state is frozen and stored. When the approver acts, the graph resumes from `await_approval` without re-running earlier nodes.

Use LangGraph's built-in checkpointing.

### 5.4 State Schema

Define the graph's `TypedDict` state explicitly. At minimum:

```python
class SQLAssistantState(TypedDict):
    session_id: str
    thread_id: str
    messages: list[BaseMessage]
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
    error: str | None
    final_response: AssistantResponse | None
```

All referenced types (`Intent`, `ValidationResult`, `RiskLevel`, etc.) must be defined as Pydantic models with field-level docstrings.

---

## 6. Database Schema

Provide and use the following schema in your sample PostgreSQL instance. Your SQL generation must target this schema.

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    full_name TEXT,
    acquisition_channel TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_test_account BOOLEAN NOT NULL DEFAULT false,
    is_deleted BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE loan_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    requested_amount NUMERIC(14, 2) NOT NULL,
    approved_amount NUMERIC(14, 2),
    status TEXT NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ,
    rejection_reason TEXT
);

CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    merchant_name TEXT,
    merchant_category TEXT,
    amount NUMERIC(14, 2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'UAH',
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sql_approval_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    requester_email TEXT NOT NULL,
    original_question TEXT NOT NULL,
    generated_sql TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    risk_justification TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    approver_email TEXT,
    approved_sql TEXT,
    rejection_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);


CREATE TABLE sql_query_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    requester_email TEXT NOT NULL,
    question TEXT NOT NULL,
    generated_sql TEXT,
    final_sql TEXT,
    risk_level TEXT,
    approval_request_id UUID REFERENCES sql_approval_queue(id),
    execution_status TEXT,
    execution_duration_ms INTEGER,
    row_count INTEGER,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Seed the database with realistic fake data (1 000–10 000 rows per table). Include at least 50 test accounts and a realistic distribution of statuses and dates spanning 2023–2025.

---

## 7. API Requirements

### 7.1 Chat Endpoints

```
POST /api/sessions
    Request:  { requester_email: str }
    Response: { session_id: str, created_at: str }

POST /api/sessions/{session_id}/messages
    Request:  { message: str, thread_id: str }
    Response: StreamingResponse (SSE) or { response: AssistantResponse }
    Note:     Streaming is preferred. Define your SSE event schema.

GET  /api/sessions/{session_id}/messages
    Response: { messages: list[MessageRecord] }

DELETE /api/sessions/{session_id}
    Response: 204
```

### 7.2 Approval Endpoints

```
GET  /api/approvals?status=pending
    Response: { items: list[ApprovalItem], total: int }
    Auth:     approver role required

GET  /api/approvals/{approval_id}
    Response: ApprovalItem

POST /api/approvals/{approval_id}/approve
    Request:  { modified_sql?: str }   ← optional; if omitted, original SQL runs
    Response: { approval_id: str, status: str }

POST /api/approvals/{approval_id}/reject
    Request:  { reason: str }           ← required
    Response: { approval_id: str, status: str }
```

### 7.3 Query History

```
GET  /api/history?session_id=...&limit=50&offset=0
    Response: { items: list[AuditEntry], total: int }

GET  /api/history/{audit_id}
    Response: AuditEntry (includes SQL, risk, timing, result summary)
```

### 7.4 Schema Introspection

```
GET  /api/schema
    Response: { tables: list[TableSchema] }
    Note:     Used by the frontend to help users discover available data.
```

All endpoints must return typed responses. Use Pydantic response models.  
Authentication is simplified: pass `X-User-Email` and `X-User-Role` headers (`analyst` | `approver`). No OAuth required.

---

## 8. Frontend Requirements

Build a minimal but functional React frontend. This is an internal tool - prioritise function over form. The UI must include:

### 8.1 Chat Panel

- Message input with send-on-Enter.
- Conversation history in the current session.
- Each assistant response must show:
  - The natural-language answer / result summary.
  - A collapsible block containing the generated SQL (syntax-highlighted).
  - Risk level badge (`LOW` / `MEDIUM` / `HIGH`) with tooltip showing justification.
  - Result table (paginated, max 100 rows visible) with column sorting.
  - CSV export button.
- Pending-approval messages must show a spinner/status indicator that resolves when the approver acts (no full-page reload).
- Rejection messages must show the approver's reason.

### 8.2 Approval Panel

- Visible only to users with `X-User-Role: approver`.
- List of pending queries: requester, question, risk level, timestamp.
- Detail view: original question, generated SQL (editable text area for modification), risk justification, requester info.
- Approve / Approve with changes / Reject buttons.

### 8.3 History Panel

- Table of past queries: question, SQL (truncated), risk, status, execution time.
- Click-through to full detail.
- Session filter.

### 8.4 Schema Explorer (optional but encouraged)

- Collapsible tree of tables and columns so non-technical users can understand what data is available.

---

## 9. Validation and Safety Requirements

| Requirement | Detail |
|-------------|--------|
| Forbidden operations | Block at static analysis, not at DB level. Return a structured error, never execute. |
| Schema hallucinations | If generated SQL references a non-existent table or column, reject and retry, do not execute. |
| Prompt injection | User inputs must be sanitized before being embedded in LLM prompts. Demonstrate awareness. |
| Parameterized queries | Generated SQL runs via read-only DB connection. No string interpolation of user values into executed SQL. |
| Result data isolation | Query results are never stored in the LLM context window beyond the current turn. Only structured summaries are carried forward. |
| Rate limiting | Per-session: max 20 requests per minute. Return `429` on breach. |
| Audit completeness | Every request - including blocked and failed ones - must produce an audit row. No silent failures. |

---

## 10. Observability Requirements

- **Structured logging**: every node entry/exit must emit a structured log line with `session_id`, `thread_id`, `node_name`, `duration_ms`, and `status`.
- **Timing**: `execute_query` must log actual DB execution time separately from total node time.
- **Retry tracking**: log each retry with `attempt_number`, `previous_error`, and `corrected_sql`.
- **Approval events**: log `approval.created`, `approval.approved`, `approval.rejected` with `approver_email` and `duration_from_request_ms`.
- Provide a `GET /health` endpoint that returns DB connectivity status and a sample query latency.

You are NOT required to integrate Prometheus, Grafana, or any external observability platform. Structured stdout logs are sufficient.
