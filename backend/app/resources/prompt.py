import json
from textwrap import dedent

from app.models.types import Intent


READABLE_SCHEMA_PROMPT = """
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
""".strip()


def build_parse_intent_prompt(history: list[dict[str, str]], previous_sql: str | None, question: str) -> str:
    safe_history = history[-6:] if history else []

    return dedent(
        f"""
        You are parsing an analytics chat message into a resolved intent.

        Return valid JSON only.
        Do not use markdown.
        Do not add explanations.

        Expected JSON shape:
        {{
          "question": "resolved user question",
          "is_follow_up": true,
          "assumptions": ["assumption 1"]
        }}

        Rules:
        - Resolve follow-up questions using the previous SQL context.
        - Do not include raw query results in the intent.
        - Keep the resolved question concise.

        Previous safe conversation summary:
        {json.dumps(safe_history, ensure_ascii=False)}

        Previous SQL, if any:
        {previous_sql or ""}

        Current user message:
        {question}
        """
    ).strip()


def build_generate_sql_prompt(
    intent: Intent,
    schema_context: str,
    previous_error: str | None = None,
    previous_sql: str | None = None,
) -> str:
    return dedent(
        f"""
        You are an internal analytics SQL assistant.
        Generate exactly one PostgreSQL SELECT statement.

        Rules:
        - Use only the allowed schema.
        - Never use INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER, GRANT,
          REVOKE, EXEC, CALL, CREATE.
        - Include a leading block comment:
          /*
          Tables used: ...
          Reason: ...
          */
        - If the request is ambiguous, choose a safe default and keep it
          bounded with LIMIT.
        - Prefer excluding users.is_deleted = false when using users unless
          the question says otherwise.
        - If user asks for all rows/everything, still generate a SELECT, but
          do not force safety; validator/risk flow will route it.
        - PostgreSQL INTERVAL literals only accept units like day, week,
          month, year (and their plurals) — "quarter" is NOT a valid
          INTERVAL unit and will raise a syntax error. For "last quarter" or
          similar, use date_trunc('quarter', CURRENT_DATE) combined with
          INTERVAL '3 months', e.g.:
          created_at >= date_trunc('quarter', CURRENT_DATE) - INTERVAL '3 months'
          AND created_at < date_trunc('quarter', CURRENT_DATE)
        - Return SQL only, no markdown.

        Allowed schema:
        {schema_context}

        Resolved intent:
        {intent.model_dump_json()}

        Previous SQL context:
        {intent.referenced_previous_sql or ""}

        Previous error to fix, if any:
        {previous_error or ""}

        Previous SQL to correct, if any:
        {previous_sql or ""}
        """
    ).strip()
