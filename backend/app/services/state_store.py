import json

from app.db.pool import get_pool
from app.models.types import SQLAssistantState
from app.resources.sql_query import GET_GRAPH_STATE_SQL, UPSERT_GRAPH_STATE_SQL


async def save_state(state: SQLAssistantState) -> None:
    pool = get_pool()
    payload = state.model_dump(mode="json")

    async with pool.acquire() as conn:
        await conn.execute(
            UPSERT_GRAPH_STATE_SQL,
            state.session_id,
            state.thread_id,
            json.dumps(payload),
        )


async def load_state(
    session_id: str,
    thread_id: str,
) -> SQLAssistantState | None:
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            GET_GRAPH_STATE_SQL,
            session_id,
            thread_id,
        )

    if not row:
        return None

    payload = row["state_json"]

    if isinstance(payload, str):
        payload = json.loads(payload)

    return SQLAssistantState.model_validate(payload)
