from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, SQLModel, create_engine, select

from jobscouter.db.models import Job
from jobscouter.schemas.job import JobPayload
from jobscouter.services.ingestion import JobIngestionService


def test_ingestion_is_idempotent() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    payload = JobPayload(
        external_id="abc-123",
        title="Backend Engineer",
        company="Acme",
        url="https://example.com/jobs/abc-123",
        source="remoteok",
        description_raw="desc",
        location="Remote",
        salary="USD 100,000 - USD 120,000",
        created_at=datetime.now(timezone.utc),
    )

    with Session(engine) as session:
        service = JobIngestionService(session)
        first = service.upsert_job(payload)
        second = service.upsert_job(payload)
        session.commit()

    assert first == "inserted"
    assert second == "skipped"

    with Session(engine) as session:
        rows = session.exec(select(Job)).all()
        assert len(rows) == 1
