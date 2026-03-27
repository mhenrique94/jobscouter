from __future__ import annotations

from datetime import datetime, timezone

from jobscouter.schemas.job import JobPayload
from jobscouter.scrapers.base import BaseScraper


class RemoteOKScraper(BaseScraper):
    source_name = "remoteok"

    async def fetch_jobs(self, limit: int | None = None) -> list[JobPayload]:
        payload = await self._get_json(self.settings.remoteok_api_url)
        jobs: list[JobPayload] = []

        for entry in payload:
            if not isinstance(entry, dict) or "id" not in entry or "position" not in entry:
                continue

            normalized = self._normalize_job(entry)
            if normalized is None:
                continue

            jobs.append(normalized)
            if limit is not None and len(jobs) >= limit:
                break

        self.logger.info("RemoteOK retornou %s vagas normalizadas", len(jobs))
        return jobs

    def _normalize_job(self, entry: dict) -> JobPayload | None:
        title = entry.get("position")
        company = entry.get("company")
        url = entry.get("url") or entry.get("apply_url")

        if not title or not company or not url:
            self.logger.warning("Registro RemoteOK ignorado por campos obrigatorios ausentes: %s", entry.get("id"))
            return None

        return JobPayload(
            external_id=str(entry["id"]),
            title=title,
            company=company,
            url=url,
            source=self.source_name,
            description_raw=entry.get("description") or "",
            location=entry.get("location") or None,
            salary=self._format_salary(entry),
            created_at=self._parse_date(entry.get("date")),
        )

    def _format_salary(self, entry: dict) -> str | None:
        salary_min = entry.get("salary_min") or 0
        salary_max = entry.get("salary_max") or 0

        if not salary_min and not salary_max:
            return None
        if salary_min and salary_max:
            return f"USD {salary_min:,} - USD {salary_max:,}"
        if salary_min:
            return f"USD {salary_min:,}+"
        return f"USD up to {salary_max:,}"

    def _parse_date(self, value: str | None) -> datetime:
        if not value:
            return datetime.now(timezone.utc)

        try:
            return datetime.fromisoformat(value)
        except ValueError:
            self.logger.warning("Data invalida na RemoteOK: %s", value)
            return datetime.now(timezone.utc)
