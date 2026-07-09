from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/ai_sql_assistant",
        validation_alias="DATABASE_URL",
    )
    openai_api_key: str | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        validation_alias="OPENAI_MODEL",
    )
    use_mock_llm: bool = Field(
        default=True,
        validation_alias="USE_MOCK_LLM",
    )
    query_timeout_seconds: int = Field(
        default=30,
        validation_alias="QUERY_TIMEOUT_SECONDS",
    )
    max_result_rows: int = Field(
        default=1000,
        validation_alias="MAX_RESULT_ROWS",
    )
    approval_timeout_minutes: int = Field(
        default=60,
        validation_alias="APPROVAL_TIMEOUT_MINUTES",
    )
    cors_origins: str = Field(
        default="http://localhost:5173",
        validation_alias="CORS_ORIGINS",
    )
    request_rate_limit_per_minute: int = Field(
        default=20,
        validation_alias="REQUEST_RATE_LIMIT_PER_MINUTE",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
