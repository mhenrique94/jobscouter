from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from sqlmodel import select

from jobscouter.core.config import get_settings
from jobscouter.core.logging import configure_logging, get_logger
from jobscouter.db.models import Job, JobStatus
from jobscouter.db.session import session_scope
from jobscouter.services.analyzer import AIAnalyzerService


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("O valor deve ser um inteiro positivo.")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Executa a analise de IA para vagas ready_for_ai.")
    parser.add_argument(
        "--limit", type=_positive_int, default=None, help="Limite de vagas para analisar."
    )
    return parser


async def run_analysis(limit: int | None) -> None:
    logger = get_logger("jobscouter.analyze_main")

    with session_scope() as session:
        service = AIAnalyzerService(session)

        statement = select(Job).where(Job.status == JobStatus.ready_for_ai)
        if limit is not None:
            statement = statement.limit(limit)

        jobs = session.exec(statement).all()
        logger.info("Vagas pendentes de analise: %s", len(jobs))

        analyzed = 0
        failed = 0

        for job in jobs:
            try:
                result = await service.analyze_job(job)
                now = datetime.now(UTC)

                job.ai_score = result.score
                job.ai_summary = result.summary
                job.ai_analysis_at = now
                job.status = JobStatus.analyzed
                job.updated_at = now

                session.add(job)
                session.flush()
                analyzed += 1
            except Exception as exc:
                failed += 1
                logger.exception("Falha ao analisar vaga id=%s url=%s: %s", job.id, job.url, exc)
                continue

        logger.info("Analise concluida | analyzed=%s failed=%s", analyzed, failed)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_analysis(limit=args.limit))


if __name__ == "__main__":
    main()
