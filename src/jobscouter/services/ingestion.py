from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import Session, select

from jobscouter.core.logging import get_logger
from jobscouter.db.models import Job
from jobscouter.schemas.job import JobPayload


@dataclass(slots=True)
class IngestionStats:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0


class JobIngestionService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.logger = get_logger("jobscouter.services.ingestion")

    def ingest_jobs(self, jobs: list[JobPayload]) -> IngestionStats:
        stats = IngestionStats()
        for job in jobs:
            try:
                outcome = self.upsert_job(job)
            except Exception as exc:
                stats.failed += 1
                self.logger.exception("Falha ao persistir vaga %s: %s", job.url, exc)
                continue

            if outcome == "inserted":
                stats.inserted += 1
            elif outcome == "updated":
                stats.updated += 1
            else:
                stats.skipped += 1

        self.logger.info(
            "Ingestao concluida | inserted=%s updated=%s skipped=%s failed=%s",
            stats.inserted,
            stats.updated,
            stats.skipped,
            stats.failed,
        )
        return stats

    def upsert_job(self, payload: JobPayload) -> str:
        existing = self._find_existing_job(payload)
        if existing is None:
            self.session.add(self._build_model(payload))
            self.session.flush()
            return "inserted"

        changed = False
        for field in ["title", "company", "url", "description_raw", "location", "salary", "created_at"]:
            incoming_value = getattr(payload, field)
            current_value = getattr(existing, field)
            if not self._values_equal(current_value, incoming_value):
                setattr(existing, field, incoming_value)
                changed = True

        if changed:
            existing.updated_at = datetime.now(timezone.utc)
            existing.last_seen_at = datetime.now(timezone.utc)
            self.session.add(existing)
            self.session.flush()
            return "updated"

        return "skipped"

    def _find_existing_job(self, payload: JobPayload) -> Job | None:
        if payload.external_id:
            statement = select(Job).where(
                Job.source == payload.source,
                Job.external_id == payload.external_id,
            )
            job = self.session.exec(statement).first()
            if job is not None:
                return job

        statement = select(Job).where(Job.source == payload.source, Job.url == payload.url)
        return self.session.exec(statement).first()

    def _build_model(self, payload: JobPayload) -> Job:
        now = datetime.now(timezone.utc)
        return Job(
            external_id=payload.external_id,
            title=payload.title,
            company=payload.company,
            url=payload.url,
            source=payload.source,
            description_raw=payload.description_raw,
            location=payload.location,
            salary=payload.salary,
            created_at=payload.created_at,
            first_seen_at=now,
            last_seen_at=now,
            updated_at=now,
        )

    def _values_equal(self, current_value: object, incoming_value: object) -> bool:
        if isinstance(current_value, datetime) and isinstance(incoming_value, datetime):
            return self._normalize_datetime(current_value) == self._normalize_datetime(incoming_value)
        return current_value == incoming_value

    def _normalize_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
