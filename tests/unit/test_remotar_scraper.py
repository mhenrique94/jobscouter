from __future__ import annotations

import httpx
import pytest

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
        user_agent="test-agent",
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
