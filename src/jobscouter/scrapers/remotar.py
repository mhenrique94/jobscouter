from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from jobscouter.schemas.job import JobPayload
from jobscouter.scrapers.base import BaseScraper


JOB_PATH_PREFIX = "/job/"
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
    api_payload: dict | None = None


class RemotarScraper(BaseScraper):
    source_name = "remotar"

    async def fetch_jobs(self, limit: int | None = None) -> list[JobPayload]:
        html = await self._get_text(self.settings.remotar_base_url)
        listings = self._extract_listing_items(html)
        if not listings:
            listings = await self._extract_listing_items_from_api(limit=limit)

        jobs: list[JobPayload] = []

        for item in listings[:limit]:
            try:
                if item.api_payload is not None:
                    jobs.append(self._normalize_api_job(item.api_payload))
                else:
                    jobs.append(await self._fetch_job_detail(item))
            except Exception as exc:
                self.logger.exception("Falha ao processar vaga Remotar %s: %s", item.url, exc)

        self.logger.info("Remotar retornou %s vagas normalizadas", len(jobs))
        return jobs

    def _extract_listing_items(self, html: str) -> list[RemotarListingItem]:
        soup = BeautifulSoup(html, "html.parser")
        seen_urls: set[str] = set()
        items: list[RemotarListingItem] = []

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if JOB_PATH_PREFIX not in href:
                continue

            absolute_url = urljoin(self.settings.remotar_base_url, href)
            if absolute_url in seen_urls:
                continue

            external_id = self._extract_job_id(absolute_url)
            title = anchor.get_text(" ", strip=True)
            if not title:
                self.logger.warning("Link de vaga Remotar sem titulo: %s", absolute_url)
                continue

            company = self._find_company(anchor)
            items.append(
                RemotarListingItem(
                    external_id=external_id,
                    title=title,
                    company=company,
                    url=absolute_url,
                )
            )
            seen_urls.add(absolute_url)

        if not items:
            self.logger.warning("Nenhuma vaga foi encontrada na pagina da Remotar; possivel mudanca no HTML")

        return items

    async def _extract_listing_items_from_api(self, limit: int | None = None) -> list[RemotarListingItem]:
        api_url = f"{self.settings.remotar_api_url}/jobs"
        params: dict[str, int | str] = {"active": "true", "page": 1}
        if limit is not None:
            params["limit"] = limit

        data = await self._get_json(f"{api_url}?" + "&".join(f"{k}={v}" for k, v in params.items()))
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            self.logger.warning("Resposta inesperada da API da Remotar ao buscar listagem")
            return []

        items: list[RemotarListingItem] = []
        for row in rows:
            if not isinstance(row, dict):
                continue

            job_id = row.get("id")
            title = row.get("title")
            if not job_id or not title:
                continue

            company = None
            if isinstance(row.get("company"), dict):
                company = row["company"].get("name")
            company = company or row.get("companyDisplayName")

            url = row.get("externalLink") or f"{self.settings.remotar_base_url}/job/{job_id}"
            items.append(
                RemotarListingItem(
                    external_id=str(job_id),
                    title=title,
                    company=company,
                    url=url,
                    api_payload=row,
                )
            )

        self.logger.info("Listagem da Remotar carregada via API com %s vagas", len(items))
        return items

    async def _fetch_job_detail(self, item: RemotarListingItem) -> JobPayload:
        html = await self._get_text(item.url)
        soup = BeautifulSoup(html, "html.parser")

        title = self._first_text(soup, ["h1"]) or item.title
        company = self._company_from_detail(soup) or item.company
        if not company:
            self.logger.warning("Empresa nao encontrada na vaga Remotar %s", item.url)
            company = "Empresa nao informada"

        description_raw = self._extract_description(soup)
        location = self._extract_location(soup)
        salary = self._extract_salary(soup)

        return JobPayload(
            external_id=item.external_id,
            title=title,
            company=company,
            url=item.url,
            source=self.source_name,
            description_raw=description_raw,
            location=location,
            salary=salary,
            created_at=datetime.now(timezone.utc),
        )

    def _extract_job_id(self, url: str) -> str:
        match = re.search(r"/job/(\d+)/", url)
        return match.group(1) if match else url

    def _find_company(self, anchor: Tag) -> str | None:
        container = anchor.find_parent(["article", "section", "div", "li"]) or anchor.parent
        if container is None:
            return None

        company_link = container.find("a", href=re.compile(r"/company/"))
        if company_link:
            return company_link.get_text(" ", strip=True) or None
        return None

    def _company_from_detail(self, soup: BeautifulSoup) -> str | None:
        link = soup.find("a", href=re.compile(r"/company/"))
        if link:
            text = link.get_text(" ", strip=True)
            if text:
                return text
        return None

    def _extract_description(self, soup: BeautifulSoup) -> str:
        for selector in ["main", "article", "section"]:
            node = soup.select_one(selector)
            if node and isinstance(node, Tag):
                html = node.decode_contents().strip()
                if html:
                    return html

        self.logger.warning("Descricao nao encontrada na Remotar; usando body como fallback")
        body = soup.body
        return body.decode_contents().strip() if body else ""

    def _extract_location(self, soup: BeautifulSoup) -> str | None:
        page_text = soup.get_text(" ", strip=True)
        if "100% Remoto" in page_text:
            return "100% Remoto"
        if "Remoto" in page_text:
            return "Remoto"
        return None

    def _extract_salary(self, soup: BeautifulSoup) -> str | None:
        match = SALARY_PATTERN.search(soup.get_text(" ", strip=True))
        return match.group(1) if match else None

    def _first_text(self, soup: BeautifulSoup, selectors: list[str]) -> str | None:
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                text = node.get_text(" ", strip=True)
                if text:
                    return text
        return None

    def _normalize_api_job(self, row: dict) -> JobPayload:
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
            return datetime.now(timezone.utc)

        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            self.logger.warning("Data invalida na API da Remotar: %s", value)
            return datetime.now(timezone.utc)

    def _read_nested(self, data: dict, path: list[str]) -> str | None:
        current: object = data
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)

        return current if isinstance(current, str) and current else None
