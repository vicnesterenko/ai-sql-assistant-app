import json
from textwrap import dedent

from app.models.types import Intent


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
