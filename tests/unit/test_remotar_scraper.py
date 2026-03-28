from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from urllib.parse import urlparse, parse_qs

from jobscouter.core.config import Settings
from jobscouter.scrapers.remotar import RemotarScraper


LISTING_HTML = """
<html>
  <body>
    <section>
      <a href="/job/132262/sur-global-services/full-stack-developer">Full Stack Developer</a>
      <a href="/company/6495/sur-global-services">Sur Global Services</a>
    </section>
  </body>
</html>
"""

DETAIL_HTML = """
<html>
  <body>
    <main>
      <h1>Full Stack Developer</h1>
      <a href="/company/6495/sur-global-services">Sur Global Services</a>
      <p>R$ 6,000.00 a R$ 7,000.00</p>
      <span>100% Remoto</span>
      <div>
        <p>Construir APIs e frontends.</p>
      </div>
    </main>
  </body>
</html>
"""

EMPTY_HTML = """
<html>
  <body>
    <script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{}}}</script>
  </body>
</html>
"""

API_LISTING = {
    "meta": {"total": 1, "per_page": 1, "current_page": 1, "last_page": 1},
    "data": [
        {
            "id": 132279,
            "title": "Go-to-Market Engineer",
            "description": "<p>Build GTM processes</p>",
            "createdAt": "2026-03-26T16:01:06.642-03:00",
            "externalLink": "https://example.com/apply",
            "company": {"name": "TestGorilla"},
            "city": {"name": "Sao Paulo"},
            "state": {"name": "SP"},
            "country": {"name": "Brasil"},
            "jobSalary": {"from": 0, "to": 0, "currency": "BRL", "type": "uninformed"},
        }
    ],
}

API_LISTING_PAGE_1 = {
  "meta": {"total": 3, "per_page": 1, "current_page": 1, "last_page": 3},
  "data": [
    {
      "id": 1001,
      "title": "Backend Engineer I",
      "description": "<p>Backend work</p>",
      "createdAt": "2026-03-26T16:01:06.642-03:00",
      "externalLink": "https://example.com/apply/1001",
      "company": {"name": "Acme 1"},
    }
  ],
}

API_LISTING_PAGE_2 = {
  "meta": {"total": 3, "per_page": 1, "current_page": 2, "last_page": 3},
  "data": [
    {
      "id": 1002,
      "title": "Backend Engineer II",
      "description": "<p>Backend work 2</p>",
      "createdAt": "2026-03-26T16:01:06.642-03:00",
      "externalLink": "https://example.com/apply/1002",
      "company": {"name": "Acme 2"},
    }
  ],
}

API_LISTING_PAGE_3 = {
  "meta": {"total": 3, "per_page": 1, "current_page": 3, "last_page": 3},
  "data": [
    {
      "id": 1003,
      "title": "Backend Engineer III",
      "description": "<p>Backend work 3</p>",
      "createdAt": "2026-03-26T16:01:06.642-03:00",
      "externalLink": "https://example.com/apply/1003",
      "company": {"name": "Acme 3"},
    }
  ],
}


@pytest.mark.asyncio
async def test_remotar_parses_listing_and_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://remotar.com.br":
            return httpx.Response(200, text=LISTING_HTML)
        if str(request.url) == "https://remotar.com.br/job/132262/sur-global-services/full-stack-developer":
            return httpx.Response(200, text=DETAIL_HTML)
        return httpx.Response(404)

    settings = Settings(
        database_url="sqlite://",
        log_level="INFO",
        request_timeout=20,
        remoteok_api_url="https://remoteok.com/api",
        remotar_base_url="https://remotar.com.br",
        remotar_api_url="https://api.remotar.com.br",
        user_agent="test-agent",
        gemini_api_key="",
        gemini_model="gemini-1.5-flash-latest",
        gemini_retry_delay_seconds=1.5,
    )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        scraper = RemotarScraper(client=client, settings=settings)
        jobs = await scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].external_id == "132262"
    assert jobs[0].title == "Full Stack Developer"
    assert jobs[0].company == "Sur Global Services"
    assert jobs[0].location == "100% Remoto"
    assert jobs[0].salary == "R$ 6,000.00 a R$ 7,000.00"


@pytest.mark.asyncio
async def test_remotar_falls_back_to_api_when_html_has_no_jobs() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://remotar.com.br":
            return httpx.Response(200, text=EMPTY_HTML)
        if url.startswith("https://api.remotar.com.br/jobs"):
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            assert query.get("limit") == ["1"]
            return httpx.Response(200, json=API_LISTING)
        return httpx.Response(404)

    settings = Settings(
        database_url="sqlite://",
        log_level="INFO",
        request_timeout=20,
        remoteok_api_url="https://remoteok.com/api",
        remotar_base_url="https://remotar.com.br",
        remotar_api_url="https://api.remotar.com.br",
        user_agent="test-agent",
        gemini_api_key="",
        gemini_model="gemini-1.5-flash-latest",
        gemini_retry_delay_seconds=1.5,
    )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        scraper = RemotarScraper(client=client, settings=settings)
        jobs = await scraper.fetch_jobs(limit=1)

    assert len(jobs) == 1
    assert jobs[0].external_id == "132279"
    assert jobs[0].title == "Go-to-Market Engineer"
    assert jobs[0].company == "TestGorilla"
    assert jobs[0].url == "https://example.com/apply"
    assert jobs[0].location == "Sao Paulo, SP, Brasil"
    assert jobs[0].salary is None


@pytest.mark.asyncio
async def test_remotar_api_paginates_and_respects_max_pages() -> None:
    requests_by_page: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://remotar.com.br":
            return httpx.Response(200, text=EMPTY_HTML)
        if url.startswith("https://api.remotar.com.br/jobs"):
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            page = int(query.get("page", ["1"])[0])
            requests_by_page.append(page)
            if page == 1:
                return httpx.Response(200, json=API_LISTING_PAGE_1)
            if page == 2:
                return httpx.Response(200, json=API_LISTING_PAGE_2)
            if page == 3:
                return httpx.Response(200, json=API_LISTING_PAGE_3)
            return httpx.Response(200, json={"meta": {"last_page": 3}, "data": []})
        return httpx.Response(404)

    settings = Settings(
        database_url="sqlite://",
        log_level="INFO",
        request_timeout=20,
        remoteok_api_url="https://remoteok.com/api",
        remotar_base_url="https://remotar.com.br",
        remotar_api_url="https://api.remotar.com.br",
        user_agent="test-agent",
        gemini_api_key="",
        gemini_model="gemini-1.5-flash-latest",
        gemini_retry_delay_seconds=1.5,
    )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        scraper = RemotarScraper(client=client, settings=settings)
        jobs = await scraper.fetch_jobs(max_pages=2)

    assert requests_by_page == [1, 2]
    assert [job.external_id for job in jobs] == ["1001", "1002"]


@pytest.mark.asyncio
async def test_remotar_keyword_uses_api_query_directly() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://remotar.com.br/search?q=django":
            raise AssertionError("Keyword search nao deve consultar o HTML da Remotar")
        if url.startswith("https://api.remotar.com.br/jobs"):
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            assert query.get("q") == ["django"]
            return httpx.Response(200, json=API_LISTING)
        return httpx.Response(404)

    settings = Settings(
        database_url="sqlite://",
        log_level="INFO",
        request_timeout=20,
        remoteok_api_url="https://remoteok.com/api",
        remotar_base_url="https://remotar.com.br",
        remotar_api_url="https://api.remotar.com.br",
        user_agent="test-agent",
        gemini_api_key="",
        gemini_model="gemini-1.5-flash-latest",
        gemini_retry_delay_seconds=1.5,
    )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        scraper = RemotarScraper(client=client, settings=settings)
        jobs = await scraper.fetch_jobs(limit=1, keyword="django")

    assert len(jobs) == 1
    assert jobs[0].external_id == "132279"
    assert jobs[0].search_keyword == "django"


@pytest.mark.asyncio
async def test_remotar_api_stops_at_checkpoint_date() -> None:
    requests_by_page: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://remotar.com.br":
            return httpx.Response(200, text=EMPTY_HTML)
        if url.startswith("https://api.remotar.com.br/jobs"):
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            page = int(query.get("page", ["1"])[0])
            requests_by_page.append(page)
            if page == 1:
                return httpx.Response(200, json=API_LISTING_PAGE_1)
            if page == 2:
                return httpx.Response(
                    200,
                    json={
                        "meta": API_LISTING_PAGE_2["meta"],
                        "data": [
                            {
                                **API_LISTING_PAGE_2["data"][0],
                                "createdAt": "2026-03-20T10:00:00+00:00",
                            }
                        ],
                    },
                )
            return httpx.Response(200, json={"meta": {"last_page": 3}, "data": []})
        return httpx.Response(404)

    settings = Settings(
        database_url="sqlite://",
        log_level="INFO",
        request_timeout=20,
        remoteok_api_url="https://remoteok.com/api",
        remotar_base_url="https://remotar.com.br",
        remotar_api_url="https://api.remotar.com.br",
        user_agent="test-agent",
        gemini_api_key="",
        gemini_model="gemini-1.5-flash-latest",
        gemini_retry_delay_seconds=1.5,
    )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        scraper = RemotarScraper(client=client, settings=settings)
        jobs = await scraper.fetch_jobs(
            keyword="python",
            checkpoint_date=datetime(2026, 3, 26, 19, 0, 0, tzinfo=timezone.utc),
        )

    assert requests_by_page == [1, 2]
    assert [job.external_id for job in jobs] == ["1001"]
