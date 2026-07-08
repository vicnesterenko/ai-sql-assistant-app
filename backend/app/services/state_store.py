import json
from app.db.pool import get_pool
from app.models.types import SQLAssistantState


async def save_state(state: SQLAssistantState) -> None:
    pool = get_pool()
    payload = state.model_dump(mode='json')
    async with pool.acquire() as conn:
        await conn.execute(
            '''
            INSERT INTO graph_state_snapshots(session_id, thread_id, state_json, updated_at)
            VALUES($1, $2, $3::jsonb, now())
            ON CONFLICT(session_id, thread_id)
            DO UPDATE SET state_json = EXCLUDED.state_json, updated_at = now()
            ''',
            state.session_id, state.thread_id, json.dumps(payload),
        )


async def load_state(session_id: str, thread_id: str) -> SQLAssistantState | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT state_json FROM graph_state_snapshots WHERE session_id = $1 AND thread_id = $2',
            session_id, thread_id,
        )
    if not row:
        return None
    payload = row['state_json']
    if isinstance(payload, str):
        payload = json.loads(payload)
    return SQLAssistantState.model_validate(payload)
