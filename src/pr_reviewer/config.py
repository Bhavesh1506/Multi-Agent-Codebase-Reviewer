"""Environment-only settings with free, local defaults."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    llm_provider: Literal["ollama", "mock", "openai_compatible"] = "ollama"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = Field(default=60, gt=0)
    review_confidence_threshold: float = Field(default=0.75, ge=0, le=1)
    review_max_agent_steps: int = Field(default=3, ge=1, le=20)
    islands_events_dir: Path | None = None
    sqlite_path: Path = Path(".diffpulse/reviews.sqlite3")
    github_webhook_secret: str | None = None
    github_token: str | None = None
