from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from time import monotonic

import httpx
from sqlmodel import Session

from jobscouter.core.config import get_settings
from jobscouter.core.logging import configure_logging, get_logger
from jobscouter.db.session import session_scope
from jobscouter.scrapers.remotar import RemotarScraper
from jobscouter.scrapers.remoteok import RemoteOKScraper
from jobscouter.services.filter import FilterConfigService
from jobscouter.services.ingestion import IngestionStats, JobIngestionService


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("O valor deve ser um inteiro positivo.")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("O valor deve ser um numero positivo.")
    return parsed


def _load_search_terms(session: Session, filters_path: Path | None = None) -> list[str]:
    config = FilterConfigService(session, filters_path=filters_path).get_active_config()
    return list(config.search_terms)


async def run_ingestion(
    source: str,
    limit: int | None,
    max_pages: int | None,
    keyword: str | None,
    continuous: bool,
    poll_interval_seconds: float,
    max_cycles: int | None,
    max_duration_seconds: float | None,
    max_empty_cycles: int | None,
) -> None:
    settings = get_settings()
    logger = get_logger("jobscouter.main")
    cycle = 0
    empty_cycles = 0
    started_at = monotonic()
    if keyword and keyword.strip():
        search_terms = [keyword.strip()]
    else:
        with session_scope() as session:
            search_terms = _load_search_terms(session)
    if not search_terms:
        logger.warning("Nenhum termo de busca configurado; executando sem termo explicito.")
        search_terms = [""]

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
        source_labels = {
            "remoteok": "RemoteOK",
            "remotar": "Remotar",
        }

        while True:
            cycle += 1
            new_or_updated_in_cycle = 0
            logger.info("=" * 72)
            logger.info(
                "CICLO %s | fonte=%s | limit=%s",
                cycle,
                source,
                limit if limit is not None else "sem limite",
            )
            logger.info("=" * 72)
            cycle_stats = IngestionStats()
            per_source_stats: dict[str, IngestionStats] = {}

            with session_scope() as session:
                ingestion_service = JobIngestionService(session)
                for selected_source in selected_sources:
                    source_stats = IngestionStats()
                    for term_index, term in enumerate(search_terms):
                        normalized_keyword = term.strip() or None
                        checkpoint_date = ingestion_service.get_latest_job_date(
                            selected_source, normalized_keyword
                        )
                        if checkpoint_date is not None:
                            logger.info(
                                "[%s][%s] Checkpoint encontrado: %s. Vagas antigas serao ignoradas.",
                                selected_source,
                                term,
                                checkpoint_date.isoformat(),
                            )

                        logger.info(
                            "[Ingestion] Buscando vagas para o termo: '%s' na fonte '%s'...",
                            term,
                            source_labels.get(selected_source, selected_source),
                        )
                        jobs = await scrapers[selected_source].fetch_jobs(
                            limit=limit,
                            max_pages=max_pages if selected_source == "remotar" else None,
                            keyword=term,
                            checkpoint_date=checkpoint_date,
                        )
                        stats = await ingestion_service.ingest_jobs(jobs)
                        source_stats.add(stats)
                        cycle_stats.add(stats)
                        logger.info("[%s][%s] %s", selected_source, term, stats.to_pretty_line())
                        new_or_updated_in_cycle += stats.inserted + stats.updated

                        if term_index < len(search_terms) - 1:
                            await asyncio.sleep(2)

                    per_source_stats[selected_source] = source_stats

            logger.info("Resumo do ciclo %s:", cycle)
            for selected_source in selected_sources:
                stats = per_source_stats.get(selected_source, IngestionStats())
                logger.info("  - %-8s %s", selected_source, stats.to_pretty_line())
            logger.info("  - %-8s %s", "total", cycle_stats.to_pretty_line())

            if not continuous:
                logger.info("Modo continuo desativado. Encerrando apos o primeiro ciclo.")
                break

            if max_cycles is not None and cycle >= max_cycles:
                logger.info("Encerrando: max_cycles atingido (%s).", max_cycles)
                break

            elapsed_seconds = monotonic() - started_at
            if max_duration_seconds is not None and elapsed_seconds >= max_duration_seconds:
                logger.info("Encerrando: max_duration_seconds atingido (%s).", max_duration_seconds)
                break

            if max_empty_cycles is not None:
                if new_or_updated_in_cycle == 0:
                    empty_cycles += 1
                    logger.info(
                        "Ciclo %s sem vagas novas/atualizadas (%s/%s ciclos vazios).",
                        cycle,
                        empty_cycles,
                        max_empty_cycles,
                    )
                else:
                    empty_cycles = 0

                if empty_cycles >= max_empty_cycles:
                    logger.info("Encerrando: max_empty_cycles atingido (%s).", max_empty_cycles)
                    break

            logger.info("Aguardando %s segundos para o proximo ciclo.", poll_interval_seconds)
            await asyncio.sleep(poll_interval_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Executa a ingestao de vagas do Jobscouter.")
    parser.add_argument(
        "--source",
        choices=["all", "remoteok", "remotar"],
        default="all",
        help="Fonte especifica a ser executada.",
    )
    parser.add_argument(
        "--limit", type=_positive_int, default=None, help="Limita a quantidade de vagas por fonte."
    )
    parser.add_argument(
        "--keyword",
        type=str,
        default=None,
        help="Termo de busca explicito. Quando ausente, usa search_terms do filters.yaml.",
    )
    parser.add_argument(
        "--max-pages",
        type=_positive_int,
        default=None,
        help="Quantidade maxima de paginas na listagem via API da Remotar.",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Mantem a busca rodando em ciclos ate atingir um criterio de parada.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=_positive_float,
        default=300,
        help="Intervalo entre ciclos em modo continuo.",
    )
    parser.add_argument(
        "--max-cycles",
        type=_positive_int,
        default=None,
        help="Quantidade maxima de ciclos no modo continuo.",
    )
    parser.add_argument(
        "--max-duration-seconds",
        type=_positive_float,
        default=None,
        help="Tempo maximo total de execucao no modo continuo.",
    )
    parser.add_argument(
        "--max-empty-cycles",
        type=_positive_int,
        default=None,
        help="Encerra apos N ciclos seguidos sem vagas novas/atualizadas.",
    )
    return parser


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    parser = build_parser()
    args = parser.parse_args()
    if not args.continuous:
        if (
            args.max_cycles is not None
            or args.max_duration_seconds is not None
            or args.max_empty_cycles is not None
        ):
            parser.error(
                "--max-cycles, --max-duration-seconds e --max-empty-cycles exigem --continuous."
            )

    asyncio.run(
        run_ingestion(
            source=args.source,
            limit=args.limit,
            max_pages=args.max_pages,
            keyword=args.keyword,
            continuous=args.continuous,
            poll_interval_seconds=args.poll_interval_seconds,
            max_cycles=args.max_cycles,
            max_duration_seconds=args.max_duration_seconds,
            max_empty_cycles=args.max_empty_cycles,
        )
    )


if __name__ == "__main__":
    main()
