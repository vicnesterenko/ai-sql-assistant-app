import json
from typing import Any

from app.db.pool import get_pool
from app.models.types import AssistantResponse
from app.resources.sql_query import (
    CREATE_SESSION_SQL,
    DELETE_SESSION_MESSAGES_SQL,
    DELETE_SESSION_SQL,
    DELETE_SESSION_STATE_SQL,
    GET_SESSION_SQL,
    LAST_SUCCESSFUL_SQL,
    LIST_MESSAGES_SQL,
    RECENT_CONTEXT_SQL,
    RESOLVE_PENDING_APPROVAL_MESSAGE_SQL,
    SAVE_MESSAGE_SQL,
)


async def create_session(requester_email: str) -> dict:
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            CREATE_SESSION_SQL,
            requester_email,
        )

    return dict(row)


async def get_session(session_id: str) -> dict | None:
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            GET_SESSION_SQL,
            session_id,
        )

    return dict(row) if row else None


async def delete_session(session_id: str) -> None:
    pool = get_pool()

    async with pool.acquire() as conn:
        await conn.execute(DELETE_SESSION_MESSAGES_SQL, session_id)
        await conn.execute(DELETE_SESSION_STATE_SQL, session_id)
        await conn.execute(DELETE_SESSION_SQL, session_id)


async def save_message(
    session_id: str,
    thread_id: str,
    role: str,
    content: str,
    response: AssistantResponse | None = None,
) -> str:
    pool = get_pool()
    response_json = response.model_dump(mode="json") if response else None

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            SAVE_MESSAGE_SQL,
            session_id,
            thread_id,
            role,
            content,
            json.dumps(response_json) if response_json else None,
        )

    return row["id"]


async def resolve_pending_approval_message(
    session_id: str,
    thread_id: str,
    approval_id: str,
    response: AssistantResponse,
) -> str:
    """Replace the pending approval message with the final result.

    If the pending message is not found, append a new assistant message.
    """
    pool = get_pool()
    response_json = response.model_dump(mode="json")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            RESOLVE_PENDING_APPROVAL_MESSAGE_SQL,
            session_id,
            thread_id,
            approval_id,
            response.message,
            json.dumps(response_json),
        )

    if row:
        return row["id"]

    return await save_message(
        session_id=session_id,
        thread_id=thread_id,
        role="assistant",
        content=response.message,
        response=response,
    )


async def list_messages(session_id: str) -> list[dict[str, Any]]:
    pool = get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            LIST_MESSAGES_SQL,
            session_id,
        )

    result: list[dict[str, Any]] = []

    for row in rows:
        item = dict(row)

        if item.get("response_json"):
            response_json = item.pop("response_json")

            if isinstance(response_json, str):
                response_json = json.loads(response_json)

            item["response"] = response_json
        else:
            item["response"] = None
            item.pop("response_json", None)

        result.append(item)

    return result


async def recent_context(
    session_id: str,
    limit: int = 8,
) -> list[dict[str, str]]:
    pool = get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            RECENT_CONTEXT_SQL,
            session_id,
            limit,
        )

    messages: list[dict[str, str]] = []

    for row in reversed(rows):
        content = row["content"]
        response_json = row["response_json"]

        if isinstance(response_json, str):
            response_json = json.loads(response_json)

        if row["role"] == "assistant" and response_json:
            content = json.dumps(
                {
                    "message": response_json.get("message"),
                    "sql": response_json.get("sql"),
                    "risk_level": response_json.get("risk_level"),
                    "assumptions": response_json.get("assumptions", []),
                },
                ensure_ascii=False,
            )

        messages.append(
            {
                "role": row["role"],
                "content": content,
            }
        )

    return messages


async def last_successful_sql(session_id: str) -> str | None:
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            LAST_SUCCESSFUL_SQL,
            session_id,
        )

    return row["final_sql"] if row else None
