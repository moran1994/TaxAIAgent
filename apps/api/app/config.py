"""Application settings — secrets via env only."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    database_url: str = "sqlite:///./data/taxai.db"
    llm_api_key: str = ""
    llm_api_base: str = ""
    llm_model: str = "gpt-4o-mini"
    disclaimer_path: str = "../../ops/m0/disclaimer-and-refusal.md"
    payment_provider: str = "mock"  # mock | wechat
    payment_force_fail: bool = False
    wechat_mch_id: str = ""
    wechat_api_key: str = ""
    wechat_app_id: str = ""
    expert_ratio: float = 0.70
    demo_expert_password: str = "demo1234"


@lru_cache
def get_settings() -> Settings:
    return Settings()
