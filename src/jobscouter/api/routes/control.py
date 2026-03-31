from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from jobscouter.api.deps import get_session
from jobscouter.core.config import get_settings
from jobscouter.core.logging import get_logger, read_log_lines
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
    logger.info(
        "[control.ingest] Iniciando ingestao em background | source=%s limit=%s", source, limit
    )
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
                        checkpoint_date = service.get_latest_job_date(selected_source)
                        jobs = await scrapers[selected_source].fetch_jobs(
                            limit=limit,
                            max_pages=None,
                            keyword=None,
                            checkpoint_date=checkpoint_date,
                        )
                        stats = await service.ingest_jobs(jobs)
                        session.commit()
                        total_stats.add(stats)
                        logger.info(
                            "[control.ingest] Fonte=%s | %s",
                            selected_source,
                            stats.to_pretty_line(),
                        )
                    except Exception as exc:
                        session.rollback()
                        logger.exception(
                            "[control.ingest] Falha na fonte %s: %s", selected_source, exc
                        )

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
                    now = datetime.now(UTC)

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
                    logger.exception(
                        "[control.analyze] Falha ao analisar vaga id=%s url=%s: %s",
                        job.id,
                        job.url,
                        exc,
                    )

            logger.info("[control.analyze] Concluido | analyzed=%s failed=%s", analyzed, failed)
    except Exception as exc:
        logger.exception("[control.analyze] Falha inesperada na task: %s", exc)


@router.get(
    "/logs",
    summary="Retornar ultimas linhas de log",
    description="Retorna as ultimas N linhas do arquivo de log da aplicacao.",
)
def get_logs(
    lines: int = Query(default=200, ge=1, le=2000, description="Numero de linhas a retornar"),
) -> dict[str, list[str]]:
    return {"lines": read_log_lines(lines)}


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
    limit: int | None = Query(
        default=None, ge=1, description="Quantidade maxima de vagas a analisar nesta execucao."
    ),
) -> dict[str, str]:
    _ = db
    background_tasks.add_task(_run_analyze_sync, limit)
    return {"detail": "Analise iniciada em background."}


@router.post(
    "/analyze/{job_id}",
    response_model=Job,
    summary="Analisar uma vaga especifica",
    description=(
        "Executa analise de IA para uma vaga especifica e retorna a vaga atualizada. "
        "Ideal para fluxo interativo no frontend sem esperar processamento em lote."
    ),
    response_description="Vaga atualizada com score, resumo e status analyzed.",
)
async def analyze_job(
    job_id: int,
    db: Session = Depends(get_session),
) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vaga nao encontrada.")

    if job.status == JobStatus.discarded:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Vagas descartadas nao podem ser analisadas individualmente.",
        )

    service = AIAnalyzerService(session=db)

    try:
        result = await service.analyze_job(job)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Falha na analise de IA: {exc}"
        ) from exc

    now = datetime.now(UTC)
    job.ai_score = result.score
    job.ai_summary = result.summary
    job.ai_analysis_at = now
    job.status = JobStatus.analyzed
    job.updated_at = now

    db.add(job)
    db.commit()
    db.refresh(job)
    return job
