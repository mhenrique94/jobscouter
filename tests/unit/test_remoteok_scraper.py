from __future__ import annotations

import httpx
import pytest

from jobscouter.core.config import Settings
from jobscouter.scrapers.remoteok import RemoteOKScraper


@pytest.mark.asyncio
async def test_remoteok_normalizes_jobs() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://remoteok.com/api"
        return httpx.Response(
            200,
            json=[
                {"legal": "metadata"},
                {
                    "id": 123,
                    "position": "Senior Python Engineer",
                    "company": "Acme",
                    "url": "https://remoteok.com/remote-jobs/123",
                    "description": "<p>Build things</p>",
                    "location": "Remote",
                    "salary_min": 120000,
                    "salary_max": 150000,
                    "date": "2026-03-25T16:00:04+00:00",
                },
            ],
        )

    settings = Settings(
        database_url="sqlite://",
        log_level="INFO",
        request_timeout=20,
        remoteok_api_url="https://remoteok.com/api",
        remotar_base_url="https://remotar.com.br",
        remotar_api_url="https://api.remotar.com.br",
        user_agent="test-agent",
    )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        scraper = RemoteOKScraper(client=client, settings=settings)
        jobs = await scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].external_id == "123"
    assert jobs[0].title == "Senior Python Engineer"
    assert jobs[0].company == "Acme"
    assert jobs[0].source == "remoteok"
    assert jobs[0].salary == "USD 120,000 - USD 150,000"
