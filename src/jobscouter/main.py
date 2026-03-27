from __future__ import annotations

import argparse
import asyncio

import httpx

from jobscouter.core.config import get_settings
from jobscouter.core.logging import configure_logging, get_logger
from jobscouter.db.session import session_scope
from jobscouter.scrapers.remotar import RemotarScraper
from jobscouter.scrapers.remoteok import RemoteOKScraper
from jobscouter.services.ingestion import JobIngestionService


async def run_ingestion(source: str, limit: int | None) -> None:
    settings = get_settings()
    logger = get_logger("jobscouter.main")

    async with httpx.AsyncClient(
        headers={"User-Agent": settings.user_agent},
        timeout=settings.request_timeout,
        follow_redirects=True,
    ) as client:
        scrapers = {
            "remoteok": RemoteOKScraper(client=client, settings=settings),
            "remotar": RemotarScraper(client=client, settings=settings),
        }

        selected_sources = list(scrapers.keys()) if source == "all" else [source]

        with session_scope() as session:
            ingestion_service = JobIngestionService(session)
            for selected_source in selected_sources:
                logger.info("Executando scraper %s", selected_source)
                jobs = await scrapers[selected_source].fetch_jobs(limit=limit)
                stats = ingestion_service.ingest_jobs(jobs)
                logger.info("Resumo %s: %s", selected_source, stats)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Executa a ingestao de vagas do Jobscouter.")
    parser.add_argument(
        "--source",
        choices=["all", "remoteok", "remotar"],
        default="all",
        help="Fonte especifica a ser executada.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limita a quantidade de vagas por fonte.")
    return parser


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    args = build_parser().parse_args()
    asyncio.run(run_ingestion(source=args.source, limit=args.limit))


if __name__ == "__main__":
    main()
