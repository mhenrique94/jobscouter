from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session, select

from jobscouter.api.deps import get_session
from jobscouter.core.config import get_settings
from jobscouter.core.logging import get_logger, read_log_lines
from jobscouter.db.models import Job, JobStatus
from jobscouter.db.session import engine
from jobscouter.scrapers.remotar import RemotarScraper
from jobscouter.scrapers.remoteok import RemoteOKScraper
from jobscouter.services.analyzer import AIAnalyzerService
from jobscouter.services.filter import FilterConfigService, validate_job_assertiveness
from jobscouter.services.ingestion import IngestionStats, JobIngestionService
from jobscouter.services.profile_enricher import EnrichedProfile, build_enriched_profile

router = APIRouter(tags=["control"])


class JobStatusUpdatePayload(BaseModel):
    status: Literal["ready_for_ai", "discarded"]


_REDACT_PATTERNS = [
    # URLs com credenciais: postgresql+psycopg://user:senha@host
    (r"(?i)(postgres(?:ql)?(?:\+\w+)?://[^:]+:)[^@]+(@)", r"\1***\2"),
    # Chaves de API: key=AIza..., api_key=..., token=...
    (r"(?i)((?:api[_-]?key|token|secret|password|gemini_api_key)\s*[=:]\s*)\S+", r"\1***"),
    # Bearer tokens em headers HTTP
    (r"(?i)(bearer\s+)\S+", r"\1***"),
]


async def _run_ingest_sync(source: str, limit: int) -> None:
    settings = get_settings()
    logger = get_logger("jobscouter.api.control")
    logger.info(
        "[control.ingest] Iniciando ingestao em background | source=%s limit=%s", source, limit
    )
    try:
        with Session(engine) as session:
            filter_config = FilterConfigService(session).get_active_config()

        search_terms = list(filter_config.search_terms) or [""]

        enriched_profile: EnrichedProfile | None = None
        if not settings.gemini_api_key:
            logger.warning("GEMINI_API_KEY nao configurada; expansao de perfil desativada.")
        else:
            try:
                enriched_profile = await build_enriched_profile(
                    include_keywords=search_terms,
                    exclude_keywords=list(filter_config.exclude_keywords),
                    settings=settings,
                )
                logger.info(
                    "[control.ingest] Expansao de perfil concluida: %s originais, %s expandidos, %s adicionados pela IA.",
                    len(enriched_profile.original_keywords),
                    len(enriched_profile.expanded_keywords),
                    len(enriched_profile.added_by_ai),
                )
            except Exception as exc:
                logger.warning(
                    "[control.ingest] Falha ao expandir perfil via IA; usando keywords estaticas. Erro: %s",
                    exc,
                )

        effective_search_terms = (
            list(enriched_profile.expanded_keywords)
            if enriched_profile is not None
            else search_terms
        )
        expanded_set = (
            set(enriched_profile.expanded_keywords) if enriched_profile is not None else None
        )

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
                for term in effective_search_terms:
                    with Session(engine) as session:
                        service = JobIngestionService(session=session)
                        try:
                            checkpoint_date = service.get_latest_job_date(selected_source)
                            jobs = await scrapers[selected_source].fetch_jobs(
                                limit=limit,
                                max_pages=None,
                                keyword=term,
                                checkpoint_date=checkpoint_date,
                            )
                            stats = await service.ingest_jobs(jobs, expanded_keywords=expanded_set)
                            session.commit()
                            total_stats.add(stats)
                            logger.info(
                                "[control.ingest] Fonte=%s termo='%s' | %s",
                                selected_source,
                                term,
                                stats.to_pretty_line(),
                            )
                        except Exception as exc:
                            session.rollback()
                            logger.exception(
                                "[control.ingest] Falha na fonte %s termo='%s': %s",
                                selected_source,
                                term,
                                exc,
                            )

            logger.info("[control.ingest] Concluido | %s", total_stats.to_pretty_line())
    except Exception as exc:
        logger.exception("[control.ingest] Falha inesperada na task: %s", exc)


def _run_assertiveness_cleanup_sync(threshold: int) -> None:
    logger = get_logger("jobscouter.api.control")
    logger.info("[control.cleanup] Iniciando limpeza de assertividade | threshold=%s", threshold)
    _BATCH_SIZE = 200
    try:
        with Session(engine) as session:
            config = FilterConfigService(session).get_active_config()
            keywords: set[str] = {kw.casefold() for kw in config.include_keywords}

            if not keywords:
                logger.warning(
                    "[control.cleanup] Abortando: include_keywords vazio. "
                    "Configure keywords antes de executar a limpeza para evitar exclusao em massa."
                )
                return

            deleted = 0
            kept = 0
            last_id = 0

            while True:
                statement = (
                    select(Job)
                    .where(Job.status != JobStatus.analyzed, Job.id > last_id)
                    .order_by(Job.id)
                    .limit(_BATCH_SIZE)
                )
                jobs = session.exec(statement).all()
                if not jobs:
                    break

                logger.info(
                    "[control.cleanup] Processando lote | last_id=%s tamanho=%s",
                    last_id,
                    len(jobs),
                )
                last_id = jobs[-1].id

                for job in jobs:
                    content = f"{job.title}\n{job.description_raw}"
                    is_assertive, match_count = validate_job_assertiveness(
                        content, keywords, threshold
                    )
                    if not is_assertive:
                        logger.info(
                            "[control.cleanup] Excluindo vaga id=%s - matches: %s | url=%s",
                            job.id,
                            match_count,
                            job.url,
                        )
                        session.delete(job)
                        deleted += 1
                    else:
                        kept += 1

                session.commit()

            logger.info("[control.cleanup] Concluido | excluidas=%s preservadas=%s", deleted, kept)
    except Exception as exc:
        logger.exception("[control.cleanup] Falha inesperada na task: %s", exc)


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


def _redact_line(line: str) -> str:
    import re

    for pattern, replacement in _REDACT_PATTERNS:
        line = re.sub(pattern, replacement, line)
    return line


# Novo endpoint para atualizar status manualmente
@router.patch(
    "/jobs/{job_id}/status",
    response_model=Job,
    summary="Atualizar status da vaga manualmente",
    description=(
        "Permite ao usuário classificar a vaga como 'ready_for_ai' ou 'discarded' manualmente."
    ),
    response_description="Vaga atualizada com novo status.",
)
def update_job_status(
    job_id: int,
    payload: JobStatusUpdatePayload = Body(...),
    db: Session = Depends(get_session),
) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vaga nao encontrada.")

    job.status = JobStatus(payload.status)
    job.updated_at = datetime.now(UTC)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get(
    "/logs",
    summary="Retornar ultimas linhas de log",
    description="Retorna as ultimas N linhas do arquivo de log da aplicacao.",
)
def get_logs(
    lines: int = Query(default=200, ge=1, le=2000, description="Numero de linhas a retornar"),
) -> dict[str, list[str]]:
    settings = get_settings()
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Endpoint de logs indisponivel em producao.",
        )
    return {"lines": [_redact_line(line) for line in read_log_lines(lines)]}


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
    limit: int = Query(default=100, ge=1, description="Limite de vagas por fonte no ciclo atual."),
) -> dict[str, str]:
    _ = db
    background_tasks.add_task(_run_ingest_sync, source, limit)
    return {"detail": "Ingestao iniciada em background."}


@router.post(
    "/sync/cleanup-assertiveness",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Excluir vagas sem assertividade do banco",
    description=(
        "Remove do banco todas as vagas nao analisadas que nao atingem o minimo de "
        "`threshold` termos unicos de include_keywords. "
        "Vagas com status 'analyzed' sao preservadas."
    ),
    response_description="Confirmacao de que a limpeza foi enfileirada.",
)
def sync_cleanup_assertiveness(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
    threshold: int = Query(default=3, ge=1, description="Minimo de keywords unicas exigidas."),
) -> dict[str, str]:
    _ = db
    background_tasks.add_task(_run_assertiveness_cleanup_sync, threshold)
    return {"detail": "Limpeza de assertividade iniciada em background."}


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
            status_code=422,
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
