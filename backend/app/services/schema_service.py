from app.models.types import ColumnSchema, SchemaResponse, TableSchema

SCHEMA: dict[str, dict] = {
    'users': {
        'description': 'Application users and acquisition metadata.',
        'large': True,
        'sensitive': True,
        'columns': {
            'id': 'UUID primary key',
            'email': 'User email. Sensitive PII.',
            'full_name': 'Full name. Sensitive PII.',
            'acquisition_channel': 'Marketing acquisition channel.',
            'created_at': 'Signup timestamp.',
            'is_test_account': 'Marks internal/test users.',
            'is_deleted': 'Soft-delete flag.',
        },
    },
    'loan_applications': {
        'description': 'Loan application lifecycle and decision timestamps.',
        'large': True,
        'sensitive': True,
        'columns': {
            'id': 'UUID primary key',
            'user_id': 'Foreign key to users.id',
            'requested_amount': 'Requested loan amount.',
            'approved_amount': 'Approved loan amount, nullable.',
            'status': 'Application status.',
            'submitted_at': 'Submission timestamp.',
            'decided_at': 'Decision timestamp, nullable.',
            'rejection_reason': 'Reason for rejection. Sensitive business data.',
        },
    },
    'transactions': {
        'description': 'User transactions with merchant and amount data.',
        'large': True,
        'sensitive': False,
        'columns': {
            'id': 'UUID primary key',
            'user_id': 'Foreign key to users.id',
            'merchant_name': 'Merchant display name.',
            'merchant_category': 'Merchant category.',
            'amount': 'Transaction amount.',
            'currency': 'Transaction currency.',
            'status': 'Transaction status.',
            'created_at': 'Transaction timestamp.',
        },
    },
    'sql_approval_queue': {
        'description': 'Human approval queue for high-risk generated SQL.',
        'large': False,
        'sensitive': True,
        'columns': {
            'id': 'UUID primary key',
            'session_id': 'Chat session identifier.',
            'thread_id': 'LangGraph thread identifier.',
            'requester_email': 'Requester email.',
            'original_question': 'Original user question.',
            'generated_sql': 'Generated SQL awaiting review.',
            'risk_level': 'Risk level at submission time.',
            'risk_justification': 'Risk rationale.',
            'status': 'pending/approved/rejected/expired.',
            'approver_email': 'Approver email.',
            'approved_sql': 'Final SQL approved by human.',
            'rejection_reason': 'Rejection reason.',
            'created_at': 'Queue creation timestamp.',
            'resolved_at': 'Decision timestamp.',
        },
    },
    'sql_query_audit': {
        'description': 'Audit log of every query attempt.',
        'large': False,
        'sensitive': True,
        'columns': {
            'id': 'UUID primary key',
            'session_id': 'Chat session identifier.',
            'thread_id': 'LangGraph thread identifier.',
            'requester_email': 'Requester email.',
            'question': 'Question asked by user.',
            'generated_sql': 'Generated SQL.',
            'final_sql': 'Executed SQL if any.',
            'risk_level': 'Risk level.',
            'approval_request_id': 'Approval queue reference.',
            'execution_status': 'ok/error/timeout/blocked/pending/rejected.',
            'execution_duration_ms': 'DB execution time.',
            'row_count': 'Returned rows count.',
            'error_message': 'Error text.',
            'result_summary': 'Summary of result, not raw data.',
            'created_at': 'Audit timestamp.',
        },
    },
}

COLUMN_TYPES: dict[str, dict[str, str]] = {
    'users': {
        'id': 'uuid', 'email': 'text', 'full_name': 'text', 'acquisition_channel': 'text',
        'created_at': 'timestamptz', 'is_test_account': 'boolean', 'is_deleted': 'boolean'
    },
    'loan_applications': {
        'id': 'uuid', 'user_id': 'uuid', 'requested_amount': 'numeric', 'approved_amount': 'numeric',
        'status': 'text', 'submitted_at': 'timestamptz', 'decided_at': 'timestamptz', 'rejection_reason': 'text'
    },
    'transactions': {
        'id': 'uuid', 'user_id': 'uuid', 'merchant_name': 'text', 'merchant_category': 'text',
        'amount': 'numeric', 'currency': 'text', 'status': 'text', 'created_at': 'timestamptz'
    },
    'sql_approval_queue': {k: 'text' for k in SCHEMA['sql_approval_queue']['columns']},
    'sql_query_audit': {k: 'text' for k in SCHEMA['sql_query_audit']['columns']},
}

READABLE_SCHEMA_PROMPT = '''
Allowed PostgreSQL schema:

users(id UUID PK, email TEXT, full_name TEXT, acquisition_channel TEXT, created_at TIMESTAMPTZ, is_test_account BOOLEAN, is_deleted BOOLEAN)
loan_applications(id UUID PK, user_id UUID FK users.id, requested_amount NUMERIC, approved_amount NUMERIC, status TEXT, submitted_at TIMESTAMPTZ, decided_at TIMESTAMPTZ, rejection_reason TEXT)
transactions(id UUID PK, user_id UUID FK users.id, merchant_name TEXT, merchant_category TEXT, amount NUMERIC, currency TEXT, status TEXT, created_at TIMESTAMPTZ)

Business notes:
- New users means users.created_at.
- Test accounts should usually be excluded with users.is_test_account = false when the request says exclude internal/test accounts.
- Deleted users should usually be excluded with users.is_deleted = false.
- Transaction volume means SUM(transactions.amount), usually for transactions.status = 'success'.
- Loan approval time means decided_at - submitted_at for rows with decided_at IS NOT NULL.
- Return PostgreSQL SELECT only. Never use mutation statements.
'''.strip()


def get_schema_response() -> SchemaResponse:
    tables: list[TableSchema] = []
    for table_name, meta in SCHEMA.items():
        columns = []
        for col, desc in meta['columns'].items():
            columns.append(ColumnSchema(name=col, data_type=COLUMN_TYPES[table_name].get(col, 'text'), nullable=True, description=desc))
        tables.append(TableSchema(name=table_name, description=meta['description'], large=meta['large'], sensitive=meta['sensitive'], columns=columns))
    return SchemaResponse(tables=tables)


def allowed_tables() -> set[str]:
    return set(SCHEMA)


def allowed_columns(table: str) -> set[str]:
    return set(SCHEMA.get(table, {}).get('columns', {}))


def is_large_table(table: str) -> bool:
    return bool(SCHEMA.get(table, {}).get('large'))


def is_sensitive_table(table: str) -> bool:
    return bool(SCHEMA.get(table, {}).get('sensitive'))


def schema_prompt() -> str:
    return READABLE_SCHEMA_PROMPT
