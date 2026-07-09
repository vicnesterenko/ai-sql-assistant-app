CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    full_name TEXT,
    acquisition_channel TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_test_account BOOLEAN NOT NULL DEFAULT false,
    is_deleted BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS loan_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    requested_amount NUMERIC(14, 2) NOT NULL,
    approved_amount NUMERIC(14, 2),
    status TEXT NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ,
    rejection_reason TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    merchant_name TEXT,
    merchant_category TEXT,
    amount NUMERIC(14, 2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'UAH',
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sql_approval_queue (
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

CREATE TABLE IF NOT EXISTS sql_query_audit (
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
    result_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Extra app tables for sessions, messages, and graph state snapshots.
CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requester_email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    response_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS graph_state_snapshots (
    session_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    state_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, thread_id)
);

CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);
CREATE INDEX IF NOT EXISTS idx_users_acquisition_channel ON users(acquisition_channel);
CREATE INDEX IF NOT EXISTS idx_users_is_test ON users(is_test_account);
CREATE INDEX IF NOT EXISTS idx_loan_applications_user_id ON loan_applications(user_id);
CREATE INDEX IF NOT EXISTS idx_loan_applications_submitted_at ON loan_applications(submitted_at);
CREATE INDEX IF NOT EXISTS idx_loan_applications_status ON loan_applications(status);
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_transactions_merchant_name ON transactions(merchant_name);
CREATE INDEX IF NOT EXISTS idx_approval_status ON sql_approval_queue(status);
CREATE INDEX IF NOT EXISTS idx_audit_session ON sql_query_audit(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id, created_at);
