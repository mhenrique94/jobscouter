from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import httpx

from jobscouter.core.config import Settings
from jobscouter.core.logging import get_logger
from jobscouter.schemas.job import JobPayload


class BaseScraper(ABC):
    source_name: str

    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self.logger = get_logger(f"jobscouter.scrapers.{self.source_name}")

    @abstractmethod
    async def fetch_jobs(
        self,
        limit: int | None = None,
        max_pages: int | None = None,
        keyword: str | None = None,
        checkpoint_date: datetime | None = None,
    ) -> list[JobPayload]:
        raise NotImplementedError

    async def _get_text(self, url: str) -> str:
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            self.logger.exception("Falha HTTP ao buscar %s: %s", url, exc)
            raise

    async def _get_json(self, url: str) -> Any:
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            self.logger.exception("Falha HTTP ao buscar JSON em %s: %s", url, exc)
            raise
