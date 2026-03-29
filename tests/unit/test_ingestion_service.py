from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from sqlmodel import Session, SQLModel, create_engine, select

from jobscouter.db.models import Job
from jobscouter.schemas.job import JobPayload
from jobscouter.services.ingestion import IngestionResult, JobIngestionService


def test_ingestion_is_idempotent() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    payload = JobPayload(
        external_id="abc-123",
        title="Backend Engineer",
        company="Acme",
        url="https://example.com/jobs/abc-123",
        source="remoteok",
        search_keyword="python",
        description_raw="desc",
        location="Remote",
        salary="USD 100,000 - USD 120,000",
        created_at=datetime.now(UTC),
    )

    with Session(engine) as session:
        service = JobIngestionService(session)
        first = service.upsert_job(payload)
        second = service.upsert_job(payload)
        session.commit()

    assert first == IngestionResult.INSERTED
    assert second == IngestionResult.SKIPPED

    with Session(engine) as session:
        rows = session.exec(select(Job)).all()
        assert len(rows) == 1


def test_get_latest_job_date_returns_none_when_no_rows() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        service = JobIngestionService(session)
        latest = service.get_latest_job_date("remoteok")

    assert latest is None


def test_get_latest_job_date_returns_latest_across_all_keywords() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    older_python = datetime(2026, 3, 25, 10, 0, 0, tzinfo=UTC)
    newer_python = datetime(2026, 3, 26, 10, 0, 0, tzinfo=UTC)
    newer_django = datetime(2026, 3, 27, 10, 0, 0, tzinfo=UTC)

    with Session(engine) as session:
        service = JobIngestionService(session)
        service.upsert_job(
            JobPayload(
                external_id="python-1",
                title="Backend Engineer",
                company="Acme",
                url="https://example.com/jobs/python-1",
                source="remoteok",
                search_keyword="python",
                created_at=older_python,
            )
        )
        service.upsert_job(
            JobPayload(
                external_id="python-2",
                title="Backend Engineer II",
                company="Acme",
                url="https://example.com/jobs/python-2",
                source="remoteok",
                search_keyword="python",
                created_at=newer_python,
            )
        )
        service.upsert_job(
            JobPayload(
                external_id="django-1",
                title="Django Engineer",
                company="Acme",
                url="https://example.com/jobs/django-1",
                source="remoteok",
                search_keyword="django",
                created_at=newer_django,
            )
        )
        session.commit()

    with Session(engine) as session:
        service = JobIngestionService(session)
        latest = service.get_latest_job_date("remoteok")

    assert latest is not None
    assert latest.replace(tzinfo=UTC) == newer_django


def test_upsert_merges_search_keywords_for_same_job() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    base = dict(
        external_id="job-1",
        title="Backend Engineer",
        company="Acme",
        url="https://example.com/jobs/1",
        source="remoteok",
        created_at=datetime.now(UTC),
    )

    with Session(engine) as session:
        service = JobIngestionService(session)
        first = service.upsert_job(JobPayload(**base, search_keyword="python"))
        second = service.upsert_job(JobPayload(**base, search_keyword="django"))
        third = service.upsert_job(JobPayload(**base, search_keyword="python"))  # duplicado
        session.commit()

    assert first == IngestionResult.INSERTED
    assert second == IngestionResult.UPDATED
    assert third == IngestionResult.SKIPPED

    with Session(engine) as session:
        rows = session.exec(select(Job)).all()
        assert len(rows) == 1
        assert set(rows[0].search_keywords) == {"python", "django"}


def test_ingest_jobs_skips_classification_when_outcome_skipped() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    payload = JobPayload(
        external_id="abc-123",
        title="Backend Engineer",
        company="Acme",
        url="https://example.com/jobs/abc-123",
        source="remoteok",
        search_keyword="python",
        created_at=datetime.now(UTC),
    )

    with Session(engine) as session:
        service = JobIngestionService(session)
        service.filter_service.classify_job = AsyncMock(return_value=None)

        first_stats = asyncio.run(service.ingest_jobs([payload]))
        second_stats = asyncio.run(service.ingest_jobs([payload]))

        assert first_stats.inserted == 1
        assert second_stats.skipped == 1
        assert service.filter_service.classify_job.await_count == 1
