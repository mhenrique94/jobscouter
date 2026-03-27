from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlmodel import Session, select

from jobscouter.api.deps import get_session
from jobscouter.core.config import get_settings
from jobscouter.core.logging import get_logger
from jobscouter.db.models import Job, JobStatus
from jobscouter.db.session import engine
from jobscouter.scrapers.remotar import RemotarScraper
from jobscouter.scrapers.remoteok import RemoteOKScraper
from jobscouter.services.analyzer import AIAnalyzerService
from jobscouter.services.ingestion import IngestionStats, JobIngestionService


router = APIRouter(tags=["control"])


async def _run_ingest_sync(source: str, limit: int) -> None:
    settings = get_settings()
    logger = get_logger("jobscouter.api.control")
    logger.info("[control.ingest] Iniciando ingestao em background | source=%s limit=%s", source, limit)
    try:
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
            total_stats = IngestionStats()

            for selected_source in selected_sources:
                with Session(engine) as session:
                    service = JobIngestionService(session=session)
                    try:
                        checkpoint_date = service.get_latest_job_date(selected_source, None)
                        jobs = await scrapers[selected_source].fetch_jobs(
                            limit=limit,
                            max_pages=None,
                            keyword=None,
                            checkpoint_date=checkpoint_date,
                        )
                        stats = await service.ingest_jobs(jobs)
                        session.commit()
                        total_stats.add(stats)
                        logger.info("[control.ingest] Fonte=%s | %s", selected_source, stats.to_pretty_line())
                    except Exception as exc:
                        session.rollback()
                        logger.exception("[control.ingest] Falha na fonte %s: %s", selected_source, exc)

            logger.info("[control.ingest] Concluido | %s", total_stats.to_pretty_line())
    except Exception as exc:
        logger.exception("[control.ingest] Falha inesperada na task: %s", exc)


async def _run_analyze_sync(limit: int | None) -> None:
    logger = get_logger("jobscouter.api.control")
    logger.info("[control.analyze] Iniciando analise em background | limit=%s", limit)
    try:
        with Session(engine) as session:
            service = AIAnalyzerService(session=session)

            statement = select(Job).where(Job.status == JobStatus.ready_for_ai)
            if limit is not None:
                statement = statement.limit(limit)

            jobs = session.exec(statement).all()
            logger.info("[control.analyze] Vagas pendentes de analise: %s", len(jobs))

            analyzed = 0
            failed = 0
            for job in jobs:
                try:
                    result = await service.analyze_job(job)
                    now = datetime.now(timezone.utc)

                    job.ai_score = result.score
                    job.ai_summary = result.summary
                    job.ai_analysis_at = now
                    job.status = JobStatus.analyzed
                    job.updated_at = now

                    session.add(job)
                    session.commit()
                    analyzed += 1
                except Exception as exc:
                    session.rollback()
                    failed += 1
                    logger.exception("[control.analyze] Falha ao analisar vaga id=%s url=%s: %s", job.id, job.url, exc)

            logger.info("[control.analyze] Concluido | analyzed=%s failed=%s", analyzed, failed)
    except Exception as exc:
        logger.exception("[control.analyze] Falha inesperada na task: %s", exc)


@router.post(
    "/sync/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Disparar ingestao em background",
    description=(
        "Inicia o processo de coleta e persistencia de vagas em background. "
        "A resposta e imediata (202) e o progresso pode ser acompanhado pelos logs da API."
    ),
    response_description="Confirmacao de que a ingestao foi enfileirada.",
)
def sync_ingest(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
    source: Literal["all", "remoteok", "remotar"] = Query(
        default="all",
        description="Define a fonte de vagas a sincronizar.",
    ),
    limit: int = Query(default=20, ge=1, description="Limite de vagas por fonte no ciclo atual."),
) -> dict[str, str]:
    _ = db
    background_tasks.add_task(_run_ingest_sync, source, limit)
    return {"detail": "Ingestao iniciada em background."}


@router.post(
    "/sync/analyze",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Disparar analise de IA em background",
    description=(
        "Inicia a analise de vagas com status ready_for_ai em background. "
        "A resposta e imediata (202) e o resultado final e salvo no banco."
    ),
    response_description="Confirmacao de que a analise foi enfileirada.",
)
def sync_analyze(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
    limit: int | None = Query(default=None, ge=1, description="Quantidade maxima de vagas a analisar nesta execucao."),
) -> dict[str, str]:
    _ = db
    background_tasks.add_task(_run_analyze_sync, limit)
    return {"detail": "Analise iniciada em background."}
