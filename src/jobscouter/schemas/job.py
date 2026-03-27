from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    external_id: str | None = None
    title: str
    company: str
    url: str
    source: str
    description_raw: str = ""
    location: str | None = None
    salary: str | None = None
    created_at: datetime = utcnow()

    @field_validator("title", "company", "url", "source")
    @classmethod
    def not_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("field cannot be empty")
        return value

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        return value.lower()
