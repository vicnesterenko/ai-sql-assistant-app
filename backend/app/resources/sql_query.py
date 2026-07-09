# ===== Seed queries =====

COUNT_USERS_SQL = "SELECT count(*) FROM users"

INSERT_USERS_SQL = """
INSERT INTO users(
    email,
    full_name,
    acquisition_channel,
    created_at,
    is_test_account,
    is_deleted
)
SELECT *
FROM UNNEST(
    $1::text[],
    $2::text[],
    $3::text[],
    $4::timestamptz[],
    $5::boolean[],
    $6::boolean[]
)
RETURNING id, created_at
"""

INSERT_LOAN_APPLICATIONS_SQL = """
INSERT INTO loan_applications(
    user_id,
    requested_amount,
    approved_amount,
    status,
    submitted_at,
    decided_at,
    rejection_reason
)
VALUES($1, $2, $3, $4, $5, $6, $7)
"""

INSERT_TRANSACTIONS_SQL = """
INSERT INTO transactions(
    user_id,
    merchant_name,
    merchant_category,
    amount,
    currency,
    status,
    created_at
)
VALUES($1, $2, $3, $4, $5, $6, $7)
"""


# ===== Graph state queries =====

UPSERT_GRAPH_STATE_SQL = """
INSERT INTO graph_state_snapshots(
    session_id,
    thread_id,
    state_json,
    updated_at
)
VALUES($1, $2, $3::jsonb, now())
ON CONFLICT(session_id, thread_id)
DO UPDATE SET
    state_json = EXCLUDED.state_json,
    updated_at = now()
"""

GET_GRAPH_STATE_SQL = """
SELECT state_json
FROM graph_state_snapshots
WHERE session_id = $1
  AND thread_id = $2
"""


# ===== Session queries =====

CREATE_SESSION_SQL = """
INSERT INTO chat_sessions(requester_email)
VALUES($1)
RETURNING id::text, created_at::text
"""

GET_SESSION_SQL = """
SELECT
    id::text,
    requester_email,
    created_at::text
FROM chat_sessions
WHERE id = $1::uuid
"""

DELETE_SESSION_MESSAGES_SQL = """
DELETE FROM chat_messages
WHERE session_id = $1
"""

DELETE_SESSION_STATE_SQL = """
DELETE FROM graph_state_snapshots
WHERE session_id = $1
"""

DELETE_SESSION_SQL = """
DELETE FROM chat_sessions
WHERE id = $1::uuid
"""

SAVE_MESSAGE_SQL = """
INSERT INTO chat_messages(
    session_id,
    thread_id,
    role,
    content,
    response_json
)
VALUES($1, $2, $3, $4, $5::jsonb)
RETURNING id::text
"""

RESOLVE_PENDING_APPROVAL_MESSAGE_SQL = """
UPDATE chat_messages
SET
    content = $4,
    response_json = $5::jsonb
WHERE id = (
    SELECT id
    FROM chat_messages
    WHERE session_id = $1
      AND thread_id = $2
      AND role = 'assistant'
      AND response_json->>'approval_request_id' = $3
    ORDER BY created_at DESC
    LIMIT 1
)
RETURNING id::text
"""

LIST_MESSAGES_SQL = """
SELECT
    id::text,
    role,
    content,
    created_at::text,
    response_json
FROM chat_messages
WHERE session_id = $1
ORDER BY created_at ASC
"""

RECENT_CONTEXT_SQL = """
SELECT
    role,
    content,
    response_json
FROM chat_messages
WHERE session_id = $1
ORDER BY created_at DESC
LIMIT $2
"""

LAST_SUCCESSFUL_SQL = """
SELECT final_sql
FROM sql_query_audit
WHERE session_id = $1
  AND execution_status = 'ok'
  AND final_sql IS NOT NULL
ORDER BY created_at DESC
LIMIT 1
"""


# ===== Audit queries =====

CREATE_AUDIT_SQL = """
INSERT INTO sql_query_audit(
    session_id,
    thread_id,
    requester_email,
    question,
    generated_sql
)
VALUES($1, $2, $3, $4, $5)
RETURNING id::text
"""

COUNT_AUDIT_ALL_SQL = """
SELECT count(*)
FROM sql_query_audit
"""

COUNT_AUDIT_BY_SESSION_SQL = """
SELECT count(*)
FROM sql_query_audit
WHERE session_id = $1
"""

LIST_AUDIT_ALL_SQL = """
SELECT
    id::text,
    session_id,
    thread_id,
    requester_email,
    question,
    generated_sql,
    final_sql,
    risk_level,
    approval_request_id::text,
    execution_status,
    execution_duration_ms,
    row_count,
    error_message,
    result_summary,
    created_at::text
FROM sql_query_audit
ORDER BY created_at DESC
LIMIT $1 OFFSET $2
"""

LIST_AUDIT_BY_SESSION_SQL = """
SELECT
    id::text,
    session_id,
    thread_id,
    requester_email,
    question,
    generated_sql,
    final_sql,
    risk_level,
    approval_request_id::text,
    execution_status,
    execution_duration_ms,
    row_count,
    error_message,
    result_summary,
    created_at::text
FROM sql_query_audit
WHERE session_id = $1
ORDER BY created_at DESC
LIMIT $2 OFFSET $3
"""

GET_AUDIT_SQL = """
SELECT
    id::text,
    session_id,
    thread_id,
    requester_email,
    question,
    generated_sql,
    final_sql,
    risk_level,
    approval_request_id::text,
    execution_status,
    execution_duration_ms,
    row_count,
    error_message,
    result_summary,
    created_at::text
FROM sql_query_audit
WHERE id = $1::uuid
"""

GET_AUDIT_BY_APPROVAL_REQUEST_SQL = """
SELECT
    id::text,
    session_id,
    thread_id,
    requester_email,
    question,
    generated_sql,
    final_sql,
    risk_level,
    approval_request_id::text,
    execution_status,
    execution_duration_ms,
    row_count,
    error_message,
    result_summary,
    created_at::text
FROM sql_query_audit
WHERE approval_request_id = $1::uuid
ORDER BY created_at DESC
LIMIT 1
"""


def build_update_audit_sql(
    updates: list[str],
    audit_id_param_number: int,
) -> str:
    return f"UPDATE sql_query_audit SET {', '.join(updates)} WHERE id = ${audit_id_param_number}::uuid"


# ===== Approval queue queries =====

APPROVAL_QUEUE_COLUMNS = """
    id::text, session_id, thread_id, requester_email, original_question, generated_sql,
    risk_level, risk_justification, status, approver_email, approved_sql, rejection_reason
""".strip()

EXPIRE_OLD_PENDING_SQL = """
UPDATE sql_approval_queue
SET status = 'expired', resolved_at = now(), rejection_reason = 'Approval timed out.'
WHERE status = 'pending'
  AND created_at < now() - ($1::int || ' minutes')::interval
RETURNING id::text, session_id, thread_id
"""

CREATE_APPROVAL_REQUEST_SQL = """
INSERT INTO sql_approval_queue(
    session_id, thread_id, requester_email, original_question, generated_sql, risk_level, risk_justification
)
VALUES($1, $2, $3, $4, $5, $6, $7)
RETURNING id::text
"""

GET_APPROVAL_SQL = f"""
SELECT {APPROVAL_QUEUE_COLUMNS}, created_at::text, resolved_at::text
FROM sql_approval_queue
WHERE id = $1::uuid
"""

COUNT_APPROVALS_BY_STATUS_SQL = "SELECT count(*) FROM sql_approval_queue WHERE status = $1"

LIST_APPROVALS_SQL = f"""
SELECT {APPROVAL_QUEUE_COLUMNS}, created_at::text, resolved_at::text
FROM sql_approval_queue
WHERE status = $1
ORDER BY created_at ASC
"""

APPROVE_APPROVAL_SQL = f"""
UPDATE sql_approval_queue
SET status = 'approved', approver_email = $2, approved_sql = COALESCE($3, generated_sql), resolved_at = now()
WHERE id = $1::uuid AND status = 'pending'
RETURNING {APPROVAL_QUEUE_COLUMNS}, created_at, created_at::text AS created_at_text, resolved_at::text
"""

REJECT_APPROVAL_SQL = f"""
UPDATE sql_approval_queue
SET status = 'rejected', approver_email = $2, rejection_reason = $3, resolved_at = now()
WHERE id = $1::uuid AND status = 'pending'
RETURNING {APPROVAL_QUEUE_COLUMNS}, created_at, created_at::text AS created_at_text, resolved_at::text
"""
