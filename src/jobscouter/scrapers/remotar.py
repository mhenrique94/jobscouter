from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

from jobscouter.schemas.job import JobPayload
from jobscouter.scrapers.base import BaseScraper

SALARY_PATTERN = re.compile(
    r"(R\$\s?[\d\.,]+(?:\s*a\s*R\$\s?[\d\.,]+)?|\$\s?[\d,\.]+(?:\s*-\s*\$\s?[\d,\.]+)?|A combinar)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class RemotarListingItem:
    external_id: str
    title: str
    company: str | None
    url: str
    created_at: datetime | None = None
    api_payload: dict | None = None


class RemotarScraper(BaseScraper):
    source_name = "remotar"

    async def fetch_jobs(
        self,
        limit: int | None = None,
        max_pages: int | None = None,
        keyword: str | None = None,
        checkpoint_date: datetime | None = None,
    ) -> list[JobPayload]:
        listings = await self._extract_listing_items_from_api(
            limit=limit,
            max_pages=max_pages,
            keyword=keyword,
            checkpoint_date=checkpoint_date,
        )

        jobs: list[JobPayload] = []
        target_items = listings[:limit] if limit is not None else listings
        for item in target_items:
            try:
                if item.api_payload is None:
                    continue
                job = self._normalize_api_job(item.api_payload, keyword)

                if checkpoint_date is not None and self._normalize_datetime(
                    job.created_at
                ) <= self._normalize_datetime(checkpoint_date):
                    self.logger.info(
                        "[Checkpoint] Vagas antigas atingidas. Interrompendo busca para %s.",
                        keyword,
                    )
                    break

                jobs.append(job)
            except Exception as exc:
                self.logger.exception("Falha ao processar vaga Remotar %s: %s", item.url, exc)

        self.logger.info("Remotar retornou %s vagas normalizadas", len(jobs))
        return jobs

    async def _extract_listing_items_from_api(
        self,
        limit: int | None = None,
        max_pages: int | None = None,
        keyword: str | None = None,
        checkpoint_date: datetime | None = None,
    ) -> list[RemotarListingItem]:
        api_url = f"{self.settings.remotar_api_url}/jobs"
        items: list[RemotarListingItem] = []
        seen_ids: set[str] = set()
        page = 1

        while True:
            if max_pages is not None and page > max_pages:
                break

            params: dict[str, int | str] = {"active": "true", "page": page}
            if limit is not None:
                params["limit"] = limit
            if keyword:
                params["q"] = keyword

            data = await self._get_json(f"{api_url}?{urlencode(params)}")
            rows = data.get("data") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                self.logger.warning("Resposta inesperada da API da Remotar ao buscar listagem")
                break

            if not rows:
                break

            for row in rows:
                if not isinstance(row, dict):
                    continue

                job_id = row.get("id")
                title = row.get("title")
                if not job_id or not title:
                    continue

                external_id = str(job_id)
                if external_id in seen_ids:
                    continue

                created_at = self._parse_datetime(row.get("createdAt"))
                if checkpoint_date is not None and self._normalize_datetime(
                    created_at
                ) <= self._normalize_datetime(checkpoint_date):
                    self.logger.info(
                        "[Checkpoint] Vagas antigas atingidas. Interrompendo busca para %s.",
                        keyword,
                    )
                    return items

                company = None
                if isinstance(row.get("company"), dict):
                    company = row["company"].get("name")
                company = company or row.get("companyDisplayName")

                url = row.get("externalLink") or f"{self.settings.remotar_base_url}/job/{job_id}"
                items.append(
                    RemotarListingItem(
                        external_id=external_id,
                        title=title,
                        company=company,
                        url=url,
                        created_at=created_at,
                        api_payload=row,
                    )
                )
                seen_ids.add(external_id)

                if limit is not None and len(items) >= limit:
                    self.logger.info("Listagem da Remotar atingiu o limite configurado (%s)", limit)
                    return items

            last_page = self._last_page_from_response(data)
            if last_page is not None and page >= last_page:
                break

            page += 1

        self.logger.info("Listagem da Remotar carregada via API com %s vagas", len(items))
        return items

    def _last_page_from_response(self, data: object) -> int | None:
        if not isinstance(data, dict):
            return None

        meta = data.get("meta")
        if not isinstance(meta, dict):
            return None

        value = meta.get("last_page")
        return value if isinstance(value, int) and value > 0 else None

    def _normalize_api_job(self, row: dict, keyword: str | None) -> JobPayload:
        job_id = row.get("id")
        title = row.get("title")
        company = self._company_from_api_row(row)
        url = row.get("externalLink") or f"{self.settings.remotar_base_url}/job/{job_id}"

        if not title or not company or not job_id:
            raise ValueError("Campos obrigatorios ausentes no payload da API da Remotar")

        return JobPayload(
            external_id=str(job_id),
            title=title,
            company=company,
            url=url,
            source=self.source_name,
            search_keyword=keyword,
            description_raw=row.get("description") or "",
            location=self._location_from_api_row(row),
            salary=self._salary_from_api_row(row),
            created_at=self._parse_datetime(row.get("createdAt")),
        )

    def _company_from_api_row(self, row: dict) -> str | None:
        company = row.get("company")
        if isinstance(company, dict):
            name = company.get("name")
            if name:
                return name
        if row.get("companyDisplayName"):
            return row["companyDisplayName"]
        return None

    def _location_from_api_row(self, row: dict) -> str | None:
        city = self._read_nested(row, ["city", "name"])
        state = self._read_nested(row, ["state", "name"])
        country = self._read_nested(row, ["country", "name"])

        parts = [part for part in [city, state, country] if part]
        if parts:
            return ", ".join(parts)

        page_hint = (row.get("subtitle") or "") + " " + (row.get("description") or "")
        if "100% Remoto" in page_hint:
            return "100% Remoto"
        if "Remoto" in page_hint:
            return "Remoto"
        return None

    def _salary_from_api_row(self, row: dict) -> str | None:
        job_salary = row.get("jobSalary")
        if isinstance(job_salary, dict):
            salary_from = job_salary.get("from") or 0
            salary_to = job_salary.get("to") or 0
            currency = (job_salary.get("currency") or "").upper() or "BRL"
            salary_type = (job_salary.get("type") or "").lower()

            if salary_type == "uninformed" and not salary_from and not salary_to:
                return None
            if salary_from and salary_to:
                return f"{currency} {salary_from:,} - {currency} {salary_to:,}"
            if salary_from:
                return f"{currency} {salary_from:,}+"
            if salary_to:
                return f"{currency} up to {salary_to:,}"

        text = " ".join([row.get("subtitle") or "", row.get("description") or ""])
        match = SALARY_PATTERN.search(text)
        return match.group(1) if match else None

    def _parse_datetime(self, value: str | None) -> datetime:
        if not value:
            return datetime.now(UTC)

        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            self.logger.warning("Data invalida na API da Remotar: %s", value)
            return datetime.now(UTC)

    def _normalize_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _read_nested(self, data: dict, path: list[str]) -> str | None:
        current: object = data
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)

        return current if isinstance(current, str) and current else None
