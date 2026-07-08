import json
from typing import Any
from app.db.pool import get_pool
from app.models.types import AssistantResponse


async def create_session(requester_email: str) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'INSERT INTO chat_sessions(requester_email) VALUES($1) RETURNING id::text, created_at::text',
            requester_email,
        )
    return dict(row)


async def get_session(session_id: str) -> dict | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT id::text, requester_email, created_at::text FROM chat_sessions WHERE id = $1::uuid', session_id)
    return dict(row) if row else None


async def delete_session(session_id: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM chat_messages WHERE session_id = $1', session_id)
        await conn.execute('DELETE FROM graph_state_snapshots WHERE session_id = $1', session_id)
        await conn.execute('DELETE FROM chat_sessions WHERE id = $1::uuid', session_id)


async def save_message(session_id: str, thread_id: str, role: str, content: str, response: AssistantResponse | None = None) -> str:
    pool = get_pool()
    response_json = response.model_dump(mode='json') if response else None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''
            INSERT INTO chat_messages(session_id, thread_id, role, content, response_json)
            VALUES($1, $2, $3, $4, $5::jsonb)
            RETURNING id::text
            ''',
            session_id, thread_id, role, content, json.dumps(response_json) if response_json else None,
        )
    return row['id']


async def resolve_pending_approval_message(session_id: str, thread_id: str, approval_id: str, response: AssistantResponse) -> str:
    """Replace the assistant's pending-approval card with the final approval result.

    This keeps the chat UI from showing a stale "Pending approval" message after
    the approver has approved/rejected the request. If the pending message is not
    found, fall back to appending a new assistant message.
    """
    pool = get_pool()
    response_json = response.model_dump(mode='json')
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE chat_messages
            SET content = $4, response_json = $5::jsonb
            WHERE id = (
                SELECT id FROM chat_messages
                WHERE session_id = $1
                  AND thread_id = $2
                  AND role = 'assistant'
                  AND response_json->>'approval_request_id' = $3
                ORDER BY created_at DESC
                LIMIT 1
            )
            RETURNING id::text
            """,
            session_id, thread_id, approval_id, response.message, json.dumps(response_json),
        )
    if row:
        return row['id']
    return await save_message(session_id, thread_id, 'assistant', response.message, response)


async def list_messages(session_id: str) -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''
            SELECT id::text, role, content, created_at::text, response_json
            FROM chat_messages WHERE session_id = $1 ORDER BY created_at ASC
            ''',
            session_id,
        )
    result = []
    for row in rows:
        item = dict(row)
        if item.get('response_json'):
            response_json = item.pop('response_json')
            if isinstance(response_json, str):
                response_json = json.loads(response_json)
            item['response'] = response_json
        else:
            item['response'] = None
            item.pop('response_json', None)
        return_item = item
        result.append(return_item)
    return result


async def recent_context(session_id: str, limit: int = 8) -> list[dict[str, str]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''
            SELECT role, content, response_json
            FROM chat_messages
            WHERE session_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            ''',
            session_id, limit,
        )
    messages: list[dict[str, str]] = []
    for row in reversed(rows):
        content = row['content']
        response_json = row['response_json']
        if isinstance(response_json, str):
            response_json = json.loads(response_json)
        if row['role'] == 'assistant' and response_json:
            # Keep only safe summary + SQL, not raw rows.
            content = json.dumps({
                'message': response_json.get('message'),
                'sql': response_json.get('sql'),
                'risk_level': response_json.get('risk_level'),
                'assumptions': response_json.get('assumptions', []),
            }, ensure_ascii=False)
        messages.append({'role': row['role'], 'content': content})
    return messages


async def last_successful_sql(session_id: str) -> str | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''
            SELECT final_sql FROM sql_query_audit
            WHERE session_id = $1 AND execution_status = 'ok' AND final_sql IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
            ''',
            session_id,
        )
    return row['final_sql'] if row else None
