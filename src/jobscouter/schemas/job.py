from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_validator

from jobscouter.db.models import Job


def utcnow() -> datetime:
    return datetime.now(UTC)


class JobPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    external_id: str | None = None
    title: str
    company: str
    url: str
    source: str
    description_raw: str = ""
    search_keyword: str | None = None
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


class PaginatedJobsResponse(BaseModel):
    items: list[Job]
    total: int
    page: int
    size: int
