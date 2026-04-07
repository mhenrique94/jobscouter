from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import func
from sqlmodel import Session, select

from jobscouter.core.logging import get_logger
from jobscouter.db.models import Job
from jobscouter.schemas.job import JobPayload
from jobscouter.services.filter import JobFilterService, validate_job_assertiveness


@dataclass(slots=True)
class IngestionStats:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    discarded: int = 0
    failed: int = 0

    def add(self, other: IngestionStats) -> None:
        self.inserted += other.inserted
        self.updated += other.updated
        self.skipped += other.skipped
        self.discarded += other.discarded
        self.failed += other.failed

    @property
    def total(self) -> int:
        return self.inserted + self.updated + self.skipped + self.discarded + self.failed

    def to_pretty_line(self) -> str:
        return (
            f"novas={self.inserted:>3} | atualizadas={self.updated:>3} "
            f"| ignoradas={self.skipped:>3} | descartadas={self.discarded:>3} | falhas={self.failed:>3}"
        )

    def __str__(self) -> str:
        return self.to_pretty_line()


class IngestionResult(str, Enum):
    INSERTED = "inserted"
    UPDATED = "updated"
    SKIPPED = "skipped"


class JobIngestionService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.logger = get_logger("jobscouter.services.ingestion")
        self.filter_service = JobFilterService(session)

    async def ingest_jobs(
        self,
        jobs: list[JobPayload],
        expanded_keywords: set[str] | None = None,
    ) -> IngestionStats:
        stats = IngestionStats()
        keywords: set[str] = (
            expanded_keywords
            if expanded_keywords is not None
            else set(self.filter_service.rules.include_keywords)
        )

        for payload in jobs:
            try:
                with self.session.begin_nested():
                    existing = self._find_existing_job(payload)

                    if existing is not None:
                        # Passo A: vaga já existe — upsert sem re-query
                        outcome, job = self._do_upsert(payload, existing)
                        if outcome == IngestionResult.UPDATED:
                            await self.filter_service.classify_job(job)
                            stats.updated += 1
                        else:
                            self.logger.debug("Vaga ignorada: duplicada | url=%s", payload.url)
                            stats.skipped += 1
                        continue

                    # Passo B: vaga nova — verificar assertividade
                    job_content = f"{payload.title}\n{payload.description_raw}"
                    is_assertive, match_count = validate_job_assertiveness(job_content, keywords)

                    if not is_assertive:
                        self.logger.info(
                            "Vaga descartada: assertividade insuficiente - matches: %s | url=%s",
                            match_count,
                            payload.url,
                        )
                        stats.discarded += 1
                        continue

                    # Passo C: INSERT + classificação
                    outcome, job = self._do_upsert(payload, existing=None)
                    await self.filter_service.classify_job(job)
                    stats.inserted += 1

            except Exception as exc:
                stats.failed += 1
                self.logger.exception("Falha ao persistir vaga %s: %s", payload.url, exc)

        self.logger.debug(
            "Ingestao concluida | inserted=%s updated=%s skipped=%s discarded=%s failed=%s",
            stats.inserted,
            stats.updated,
            stats.skipped,
            stats.discarded,
            stats.failed,
        )
        return stats

    def get_latest_job_date(self, source: str) -> datetime | None:
        statement = select(func.max(Job.created_at)).where(Job.source == source)
        return self.session.exec(statement).one()

    def upsert_job(self, payload: JobPayload) -> tuple[IngestionResult, Job]:
        existing = self._find_existing_job(payload)
        return self._do_upsert(payload, existing)

    def _do_upsert(self, payload: JobPayload, existing: Job | None) -> tuple[IngestionResult, Job]:
        if existing is None:
            job = self._build_model(payload)
            self.session.add(job)
            self.session.flush()
            return IngestionResult.INSERTED, job

        changed = False

        normalized_keyword = self._normalize_keyword(payload.search_keyword)
        current_keywords = list(existing.search_keywords or [])
        if normalized_keyword and normalized_keyword not in current_keywords:
            existing.search_keywords = [*current_keywords, normalized_keyword]
            changed = True

        for field in [
            "title",
            "company",
            "url",
            "description_raw",
            "location",
            "salary",
            "created_at",
        ]:
            incoming_value = getattr(payload, field)
            current_value = getattr(existing, field)
            if not self._values_equal(current_value, incoming_value):
                setattr(existing, field, incoming_value)
                changed = True

        if changed:
            existing.updated_at = datetime.now(UTC)
            existing.last_seen_at = datetime.now(UTC)
            self.session.add(existing)
            self.session.flush()
            return IngestionResult.UPDATED, existing

        return IngestionResult.SKIPPED, existing

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
        now = datetime.now(UTC)
        normalized_keyword = self._normalize_keyword(payload.search_keyword)
        return Job(
            external_id=payload.external_id,
            title=payload.title,
            company=payload.company,
            url=payload.url,
            source=payload.source,
            search_keywords=[normalized_keyword] if normalized_keyword else [],
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
            return self._normalize_datetime(current_value) == self._normalize_datetime(
                incoming_value
            )
        return current_value == incoming_value

    def _normalize_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _normalize_keyword(self, keyword: str | None) -> str | None:
        if keyword is None:
            return None

        normalized = keyword.strip()
        if not normalized:
            return None
        return normalized
