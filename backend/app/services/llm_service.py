import json
import re

from langchain_openai import ChatOpenAI

from app.core.logger_setup import log_event
from app.core.settings import settings
from app.models.types import Intent
from app.resources.prompt import (
    build_generate_sql_prompt,
    build_parse_intent_prompt,
)
from app.services.mock_llm_service import MockLLMService
from app.services.schema_service import schema_prompt
from app.services.sql_validation import sanitize_user_text


class LLMService:
    def __init__(self) -> None:
        self._model = None
        self._mock = MockLLMService()

        if not settings.use_mock_llm and settings.openai_api_key:
            self._model = ChatOpenAI(
                model=settings.openai_model,
                api_key=settings.openai_api_key,
                temperature=0,
            )

    async def parse_intent(
        self,
        question: str,
        history: list[dict[str, str]],
        previous_sql: str | None,
    ) -> Intent:
        question = sanitize_user_text(question)

        if self._model is None:
            return self._mock.parse_intent(
                question=question,
                previous_sql=previous_sql,
            )

        prompt = build_parse_intent_prompt(
            history=history,
            previous_sql=previous_sql,
            question=question,
        )

        try:
            msg = await self._model.ainvoke(prompt)
        except Exception as exc:
            log_event(
                "llm.parse_intent.failed",
                provider="openai",
                model=settings.openai_model,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return self._mock.parse_intent(
                question=question,
                previous_sql=previous_sql,
            )

        fallback_intent = self._mock.parse_intent(
            question=question,
            previous_sql=previous_sql,
        )

        try:
            data = json.loads(self._strip_code_fence(str(msg.content)))
        except Exception as exc:
            log_event(
                "llm.parse_intent.invalid_json",
                provider="openai",
                model=settings.openai_model,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return fallback_intent

        if not isinstance(data, dict):
            log_event(
                "llm.parse_intent.invalid_shape",
                provider="openai",
                model=settings.openai_model,
            )
            return fallback_intent

        assumptions = data.get("assumptions", [])
        if not isinstance(assumptions, list):
            assumptions = []

        is_follow_up = bool(data.get("is_follow_up", fallback_intent.is_follow_up))

        return Intent(
            question=data.get("question", question),
            is_follow_up=is_follow_up,
            assumptions=assumptions,
            referenced_previous_sql=previous_sql if is_follow_up else None,
        )

    async def generate_sql(
        self,
        intent: Intent,
        previous_error: str | None = None,
        previous_sql: str | None = None,
    ) -> str:
        if self._model is None:
            return self._mock.generate_sql(
                intent=intent,
                previous_error=previous_error,
                previous_sql=previous_sql,
            )

        prompt = build_generate_sql_prompt(
            intent=intent,
            schema_context=schema_prompt(),
            previous_error=previous_error,
            previous_sql=previous_sql,
        )

        try:
            msg = await self._model.ainvoke(prompt)
        except Exception as exc:
            log_event(
                "llm.generate_sql.failed",
                provider="openai",
                model=settings.openai_model,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return self._mock.generate_sql(
                intent=intent,
                previous_error=previous_error,
                previous_sql=previous_sql,
            )

        return self._extract_sql(str(msg.content))

    @classmethod
    def _extract_sql(cls, content: str) -> str:
        return cls._strip_code_fence(content)

    @staticmethod
    def _strip_code_fence(content: str) -> str:
        content = content.strip()
        content = re.sub(r"^```[a-zA-Z]*\s*", "", content).strip()
        content = re.sub(r"```$", "", content).strip()

        return content


llm_service = LLMService()
