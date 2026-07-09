from app.models.types import Intent
from app.resources.mock_sql_query import (
    all_users_sql,
    april_2025_new_users_by_channel_sql,
    average_loan_approval_time_q1_sql,
    default_recent_users_sql,
    delete_test_users_sql,
    merchant_volume_last_quarter_sql,
    merchant_volume_q4_2024_sql,
    signup_query_q4_2024_sql,
    users_after_january_first_sql,
)
from app.services.sql_validation import sanitize_user_text

FOLLOW_UP_MARKERS = [
    "actually",
    "now ",
    "same query",
    "same for",
    "run the same",
    "filter that",
    "exclude",
    "group that",
]


class MockLLMService:
    @staticmethod
    def parse_intent(
        question: str,
        previous_sql: str | None,
    ) -> Intent:
        question = sanitize_user_text(question)
        is_follow_up_result = MockLLMService.is_follow_up(
            question=question,
            previous_sql=previous_sql,
        )

        assumptions: list[str] = []
        resolved_question = question

        if is_follow_up_result and previous_sql:
            resolved_question = f"Follow-up to previous SQL: {question}"
            assumptions.append("I used the previous successful SQL as context for this follow-up.")

        return Intent(
            question=resolved_question,
            is_follow_up=is_follow_up_result,
            assumptions=assumptions,
            referenced_previous_sql=previous_sql if is_follow_up_result else None,
        )

    @staticmethod
    def generate_sql(
        intent: Intent,
        previous_error: str | None = None,
        previous_sql: str | None = None,
    ) -> str:
        q = intent.question.lower()
        prev = intent.referenced_previous_sql or previous_sql or ""

        if any(word in q for word in ["delete", "remove all", "drop", "truncate"]):
            return delete_test_users_sql()

        if "everything from the users" in q or "all users" in q or "give me everything" in q:
            return all_users_sql()

        if "april 2025" in q and ("new users" in q or "signed up" in q):
            return april_2025_new_users_by_channel_sql()

        if "merchant" in q and ("volume" in q or "transaction" in q):
            return merchant_volume_last_quarter_sql()

        if "average loan approval time" in q or "approval time" in q:
            return average_loan_approval_time_q1_sql()

        if ("after january 1" in q or "after jan 1" in q) and prev:
            return users_after_january_first_sql()

        if "q4 2024" in q:
            if "merchant" in prev.lower() or "transaction" in prev.lower():
                return merchant_volume_q4_2024_sql()

            return signup_query_q4_2024_sql()

        return default_recent_users_sql()

    @staticmethod
    def is_follow_up(question: str, previous_sql: str | None) -> bool:
        return bool(previous_sql and any(marker in question.lower() for marker in FOLLOW_UP_MARKERS))
