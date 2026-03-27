from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    log_level: str
    request_timeout: float
    remoteok_api_url: str
    remotar_base_url: str
    remotar_api_url: str
    user_agent: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
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
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
