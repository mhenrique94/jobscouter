from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import JSON, Column, DateTime, Index, Text, UniqueConstraint
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class JobStatus(str, Enum):
    pending = "pending"
    ready_for_ai = "ready_for_ai"
    discarded = "discarded"
    analyzed = "analyzed"


class Job(SQLModel, table=True):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint(
            "source", "external_id", "search_keyword", name="uq_jobs_source_external_id_keyword"
        ),
        UniqueConstraint("source", "url", "search_keyword", name="uq_jobs_source_url_keyword"),
        Index("ix_jobs_source_keyword_created_at", "source", "search_keyword", "created_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    external_id: str | None = Field(default=None, index=True, max_length=255)
    title: str = Field(nullable=False, max_length=255, index=True)
    company: str = Field(nullable=False, max_length=255, index=True)
    url: str = Field(sa_column=Column(Text, nullable=False))
    source: str = Field(nullable=False, max_length=50, index=True)
    search_keyword: str | None = Field(default=None, max_length=255)
    description_raw: str = Field(default="", sa_column=Column(Text, nullable=False))
    location: str | None = Field(default=None, max_length=255)
    salary: str | None = Field(default=None, max_length=255)
    status: JobStatus = Field(
        default=JobStatus.pending,
        sa_column=Column(
            SQLEnum(JobStatus, name="job_status"),
            nullable=False,
            server_default=JobStatus.pending.value,
        ),
    )
    filter_reason: str | None = Field(default=None, max_length=255)
    ai_score: int | None = Field(default=None)
    ai_summary: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    ai_analysis_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    first_seen_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    last_seen_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class FilterConfig(SQLModel, table=True):
    __tablename__ = "filter_config"

    id: int = Field(default=1, primary_key=True)
    search_terms: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    include_keywords: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    exclude_keywords: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
