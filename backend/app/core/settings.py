from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    database_url: str = Field(default='postgresql://postgres:postgres@localhost:5432/ai_sql_assistant')
    openai_api_key: str | None = None
    openai_model: str = 'gpt-4o-mini'
    use_mock_llm: bool = True
    query_timeout_seconds: int = 30
    max_result_rows: int = 1000
    approval_timeout_minutes: int = 60
    cors_origins: str = 'http://localhost:5173'
    request_rate_limit_per_minute: int = 20

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
