from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str
    database_url: str
    log_level: str
    request_timeout: float
    remoteok_api_url: str
    remotar_base_url: str
    remotar_api_url: str
    user_agent: str
    gemini_api_key: str
    gemini_model: str
    gemini_retry_delay_seconds: float

    @property
    def is_production(self) -> bool:
        return self.app_env in {"production", "prod"}

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            app_env=os.getenv("APP_ENV", "development").strip().lower(),
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql+psycopg://postgres:postgres@localhost:5432/jobscouter",
            ),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            request_timeout=float(os.getenv("REQUEST_TIMEOUT", "20")),
            remoteok_api_url=os.getenv("REMOTEOK_API_URL", "https://remoteok.com/api"),
            remotar_base_url=os.getenv("REMOTAR_BASE_URL", "https://remotar.com.br"),
            remotar_api_url=os.getenv("REMOTAR_API_URL", "https://api.remotar.com.br"),
            user_agent=os.getenv("USER_AGENT", "jobscouter-ingestion-bot/0.1"),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash-lite"),
            gemini_retry_delay_seconds=float(os.getenv("GEMINI_RETRY_DELAY_SECONDS", "1.5")),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
