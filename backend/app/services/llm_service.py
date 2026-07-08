import json
import re

from app.core.settings import settings
from app.models.types import Intent
from app.services.schema_service import schema_prompt
from app.services.sql_validation import sanitize_user_text


def _comment(tables: str, why: str) -> str:
    return f'/*\nTables used: {tables}\nReason: {why}\n*/\n'


class LLMService:
    def __init__(self) -> None:
        self._model = None
        if not settings.use_mock_llm and settings.openai_api_key:
            from langchain_openai import ChatOpenAI
            self._model = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0)

    async def parse_intent(self, question: str, history: list[dict[str, str]], previous_sql: str | None) -> Intent:
        question = sanitize_user_text(question)
        follow_up_markers = ['actually', 'now ', 'same query', 'same for', 'run the same', 'filter that', 'exclude', 'group that']
        is_follow_up = bool(previous_sql and any(marker in question.lower() for marker in follow_up_markers))

        if self._model is None:
            assumptions: list[str] = []
            resolved = question
            if is_follow_up and previous_sql:
                resolved = f'Follow-up to previous SQL: {question}'
                assumptions.append('I used the previous successful SQL as context for this follow-up.')
            return Intent(question=resolved, is_follow_up=is_follow_up, assumptions=assumptions, referenced_previous_sql=previous_sql if is_follow_up else None)

        prompt = f'''
You are parsing an analytics chat message into a resolved intent.
Return JSON only with fields: question, is_follow_up, assumptions.
Do not include raw query results in the intent.

Previous safe conversation summary:
{json.dumps(history[-6:], ensure_ascii=False)}

Previous SQL, if any:
{previous_sql or ''}

Current user message:
{question}
'''.strip()
        msg = await self._model.ainvoke(prompt)
        try:
            data = json.loads(msg.content)
        except Exception:
            data = {'question': question, 'is_follow_up': is_follow_up, 'assumptions': []}
        return Intent(
            question=data.get('question', question),
            is_follow_up=bool(data.get('is_follow_up', is_follow_up)),
            assumptions=list(data.get('assumptions', [])),
            referenced_previous_sql=previous_sql if data.get('is_follow_up', is_follow_up) else None,
        )

    async def generate_sql(self, intent: Intent, previous_error: str | None = None, previous_sql: str | None = None) -> str:
        if self._model is None:
            return self._mock_generate_sql(intent, previous_error, previous_sql)

        prompt = f'''
You are an internal analytics SQL assistant. Generate exactly one PostgreSQL SELECT statement.

Rules:
- Use only the allowed schema.
- Never use INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER, GRANT, REVOKE, EXEC, CALL, CREATE.
- Include a leading block comment:
  /*
  Tables used: ...
  Reason: ...
  */
- If the request is ambiguous, choose a safe default and keep it bounded with LIMIT.
- Prefer excluding users.is_deleted = false when using users unless the question says otherwise.
- If user asks for all rows/everything, still generate a SELECT, but do not force safety; validator/risk flow will route it.
- Return SQL only, no markdown.

{schema_prompt()}

Resolved intent:
{intent.model_dump_json()}

Previous SQL context:
{intent.referenced_previous_sql or ''}

Previous error to fix, if any:
{previous_error or ''}

Previous SQL to correct, if any:
{previous_sql or ''}
'''.strip()
        msg = await self._model.ainvoke(prompt)
        return self._extract_sql(msg.content)

    def _extract_sql(self, content: str) -> str:
        content = content.strip()
        content = re.sub(r'^```sql\s*', '', content, flags=re.I).strip()
        content = re.sub(r'^```\s*', '', content).strip()
        content = re.sub(r'```$', '', content).strip()
        return content

    def _mock_generate_sql(self, intent: Intent, previous_error: str | None, previous_sql: str | None) -> str:
        q = intent.question.lower()
        prev = intent.referenced_previous_sql or previous_sql or ''

        if any(word in q for word in ['delete', 'remove all', 'drop', 'truncate']):
            return 'DELETE FROM users WHERE is_test_account = true;'

        if 'everything from the users' in q or 'all users' in q or 'give me everything' in q:
            return _comment('users', 'The user asked for all user rows; this will be routed as high risk.') + 'SELECT * FROM users;'

        if 'april 2025' in q and ('new users' in q or 'signed up' in q):
            return _comment('users', 'Count new user signups by acquisition channel for April 2025.') + """
SELECT
    acquisition_channel,
    COUNT(*) AS new_users
FROM users
WHERE created_at >= TIMESTAMPTZ '2025-04-01'
  AND created_at < TIMESTAMPTZ '2025-05-01'
  AND is_deleted = false
GROUP BY acquisition_channel
ORDER BY new_users DESC;
""".strip()

        if 'merchant' in q and ('volume' in q or 'transaction' in q):
            return _comment('transactions, users', 'Calculate merchant transaction volume while excluding internal test accounts.') + """
SELECT
    t.merchant_name,
    SUM(t.amount) AS transaction_volume,
    COUNT(*) AS transaction_count
FROM transactions t
JOIN users u ON u.id = t.user_id
WHERE t.status = 'success'
  AND u.is_test_account = false
  AND u.is_deleted = false
  AND t.created_at >= date_trunc('quarter', CURRENT_DATE) - INTERVAL '3 months'
  AND t.created_at < date_trunc('quarter', CURRENT_DATE)
GROUP BY t.merchant_name
ORDER BY transaction_volume DESC
LIMIT 20;
""".strip()

        if 'average loan approval time' in q or 'approval time' in q:
            return _comment('loan_applications', 'Measure average time between submission and decision for applications submitted in Q1.') + """
SELECT
    ROUND(AVG(EXTRACT(EPOCH FROM (decided_at - submitted_at)) / 3600.0), 2) AS avg_approval_hours
FROM loan_applications
WHERE submitted_at >= TIMESTAMPTZ '2025-01-01'
  AND submitted_at < TIMESTAMPTZ '2025-04-01'
  AND decided_at IS NOT NULL
  AND status = 'approved';
""".strip()

        if ('after january 1' in q or 'after jan 1' in q) and prev:
            return _comment('users', 'Follow-up filter requested users signed up after January 1st.') + """
SELECT
    acquisition_channel,
    COUNT(*) AS new_users
FROM users
WHERE created_at >= TIMESTAMPTZ '2025-01-01'
  AND is_deleted = false
GROUP BY acquisition_channel
ORDER BY new_users DESC;
""".strip()

        if 'q4 2024' in q:
            if 'merchant' in prev.lower() or 'transaction' in prev.lower():
                return _comment('transactions, users', 'Repeat previous merchant volume query for Q4 2024.') + """
SELECT
    t.merchant_name,
    SUM(t.amount) AS transaction_volume,
    COUNT(*) AS transaction_count
FROM transactions t
JOIN users u ON u.id = t.user_id
WHERE t.status = 'success'
  AND u.is_test_account = false
  AND u.is_deleted = false
  AND t.created_at >= TIMESTAMPTZ '2024-10-01'
  AND t.created_at < TIMESTAMPTZ '2025-01-01'
GROUP BY t.merchant_name
ORDER BY transaction_volume DESC
LIMIT 20;
""".strip()
            return _comment('users', 'Repeat previous signup query for Q4 2024.') + """
SELECT
    acquisition_channel,
    COUNT(*) AS new_users
FROM users
WHERE created_at >= TIMESTAMPTZ '2024-10-01'
  AND created_at < TIMESTAMPTZ '2025-01-01'
  AND is_deleted = false
GROUP BY acquisition_channel
ORDER BY new_users DESC;
""".strip()

        return _comment('users', 'Ambiguous user request; default to recent non-deleted users with a safe limit.') + """
SELECT
    id,
    acquisition_channel,
    created_at,
    is_test_account
FROM users
WHERE is_deleted = false
ORDER BY created_at DESC
LIMIT 100;
""".strip()


llm_service = LLMService()
