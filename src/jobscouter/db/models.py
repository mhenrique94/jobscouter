from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Column, DateTime, Enum as SQLEnum, Index, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    pending = "pending"
    ready_for_ai = "ready_for_ai"
    discarded = "discarded"
    analyzed = "analyzed"


class Job(SQLModel, table=True):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_jobs_source_external_id"),
        UniqueConstraint("source", "url", name="uq_jobs_source_url"),
        Index("ix_jobs_source_created_at", "source", "created_at"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    external_id: Optional[str] = Field(default=None, index=True, max_length=255)
    title: str = Field(nullable=False, max_length=255, index=True)
    company: str = Field(nullable=False, max_length=255, index=True)
    url: str = Field(sa_column=Column(Text, nullable=False))
    source: str = Field(nullable=False, max_length=50, index=True)
    description_raw: str = Field(default="", sa_column=Column(Text, nullable=False))
    location: Optional[str] = Field(default=None, max_length=255)
    salary: Optional[str] = Field(default=None, max_length=255)
    status: JobStatus = Field(
        default=JobStatus.pending,
        sa_column=Column(
            SQLEnum(JobStatus, name="job_status"),
            nullable=False,
            server_default=JobStatus.pending.value,
        ),
    )
    filter_reason: Optional[str] = Field(default=None, max_length=255)
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
