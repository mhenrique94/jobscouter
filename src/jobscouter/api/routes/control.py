from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from jobscouter.api.deps import get_session
from jobscouter.core.config import get_settings
from jobscouter.core.logging import LOG_FILE, get_logger, read_log_lines
from jobscouter.core.task_registry import task_registry
from jobscouter.db.models import Job, JobStatus
from jobscouter.db.session import engine
from jobscouter.scrapers.remotar import RemotarScraper
from jobscouter.scrapers.remoteok import RemoteOKScraper
from jobscouter.services.analyzer import AIAnalyzerService
from jobscouter.services.filter import FilterConfigService, validate_job_assertiveness
from jobscouter.services.ingestion import IngestionStats, JobIngestionService
from jobscouter.services.profile_enricher import get_effective_search_terms

router = APIRouter(tags=["control"])


# ─── SSE helpers ──────────────────────────────────────────────────────────────

_LOG_PATH = Path(LOG_FILE)


def _read_new_log_lines(offset: int) -> tuple[list[str], int]:
    """Lê novas linhas do arquivo de log desde o offset informado.

    Retorna as linhas e o novo offset. Se o arquivo foi rotacionado (tamanho
    menor que o offset), reinicia o offset do zero.
    """
    try:
        size = _LOG_PATH.stat().st_size
        if size < offset:
            offset = 0  # rotação de arquivo detectada
        if size == offset:
            return [], offset
        with _LOG_PATH.open(errors="replace") as fh:
            fh.seek(offset)
            content = fh.read()
            new_offset = fh.tell()
        lines = [line.rstrip() for line in content.splitlines() if line.strip()]
        return lines, new_offset
    except OSError:
        return [], offset


@router.get(
    "/stream",
    summary="Stream de logs e status de tasks via SSE",
    description=(
        "Abre uma conexão Server-Sent Events que emite dois tipos de evento:\n"
        "- `log`: nova linha do arquivo de log\n"
        "- `tasks`: snapshot do estado atual das tasks em execução"
    ),
)
async def stream_events(request: Request) -> StreamingResponse:
    settings = get_settings()
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Endpoint de stream indisponivel em producao.",
        )

    async def generator():
        # Burst inicial: últimas 100 linhas de log
        for line in read_log_lines(100):
            yield f"event: log\ndata: {json.dumps({'line': line})}\n\n"

        # Posição atual no arquivo para iniciar o tail
        try:
            file_offset = _LOG_PATH.stat().st_size
        except OSError:
            file_offset = 0

        while not await request.is_disconnected():
            new_lines, file_offset = _read_new_log_lines(file_offset)
            for line in new_lines:
                redacted = _redact_line(line)
                yield f"event: log\ndata: {json.dumps({'line': redacted})}\n\n"

            task_registry.evict_finished()
            snapshot = task_registry.snapshot()
            yield f"event: tasks\ndata: {json.dumps(snapshot)}\n\n"

            await asyncio.sleep(0.75)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Models & helpers ──────────────────────────────────────────────────────────


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
    task_id = task_registry.start("ingest")
    logger.info(
        "[control.ingest] Iniciando ingestao em background | source=%s limit=%s", source, limit
    )
    try:
        with Session(engine) as session:
            filter_config = FilterConfigService(session).get_active_config()

        search_terms = list(filter_config.search_terms) or [""]

        effective_search_terms = await get_effective_search_terms(
            search_terms=search_terms,
            exclude_keywords=list(filter_config.exclude_keywords),
            settings=settings,
            logger=logger,
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
                with Session(engine) as ck_session:
                    checkpoint_date = JobIngestionService(session=ck_session).get_latest_job_date(
                        selected_source
                    )
                logger.info(
                    "[control.ingest] Fonte=%s | checkpoint=%s",
                    selected_source,
                    checkpoint_date.isoformat() if checkpoint_date else "nenhum",
                )

                for term_index, term in enumerate(effective_search_terms):
                    with Session(engine) as session:
                        service = JobIngestionService(session=session)
                        try:
                            jobs = await scrapers[selected_source].fetch_jobs(
                                limit=limit,
                                max_pages=None,
                                keyword=term,
                                checkpoint_date=checkpoint_date,
                            )
                            stats = await service.ingest_jobs(jobs)
                            session.commit()
                            total_stats.add(stats)
                            logger.info(
                                "[control.ingest] Fonte=%s termo='%s' | %s",
                                selected_source,
                                term,
                                stats.to_pretty_line(),
                            )
                            task_registry.update(
                                task_id,
                                f"{selected_source}/{term}: {stats.to_pretty_line()}",
                            )
                        except Exception as exc:
                            session.rollback()
                            logger.exception(
                                "[control.ingest] Falha na fonte %s termo='%s': %s",
                                selected_source,
                                term,
                                exc,
                            )

                    if term_index < len(effective_search_terms) - 1:
                        await asyncio.sleep(2)

            logger.info("[control.ingest] Concluido | %s", total_stats.to_pretty_line())
        task_registry.finish(task_id, "done")
    except Exception as exc:
        task_registry.finish(task_id, "error")
        logger.exception("[control.ingest] Falha inesperada na task: %s", exc)


def _run_assertiveness_cleanup_sync(threshold: int) -> None:
    logger = get_logger("jobscouter.api.control")
    task_id = task_registry.start("cleanup")
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
                task_registry.finish(task_id, "done")
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
                task_registry.update(task_id, f"excluidas={deleted} preservadas={kept}")

            logger.info("[control.cleanup] Concluido | excluidas=%s preservadas=%s", deleted, kept)
        task_registry.finish(task_id, "done")
    except Exception as exc:
        task_registry.finish(task_id, "error")
        logger.exception("[control.cleanup] Falha inesperada na task: %s", exc)


async def _run_analyze_sync(limit: int | None) -> None:
    logger = get_logger("jobscouter.api.control")
    task_id = task_registry.start("analyze")
    logger.info("[control.analyze] Iniciando analise em background | limit=%s", limit)
    try:
        with Session(engine) as session:
            service = AIAnalyzerService(session=session)

            statement = select(Job).where(Job.status == JobStatus.ready_for_ai)
            if limit is not None:
                statement = statement.limit(limit)

            jobs = session.exec(statement).all()
            total = len(jobs)
            logger.info("[control.analyze] Vagas pendentes de analise: %s", total)
            task_registry.update(task_id, f"0/{total} analisadas")

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
                    task_registry.update(task_id, f"{analyzed}/{total} analisadas")
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
        task_registry.finish(task_id, "done")
    except Exception as exc:
        task_registry.finish(task_id, "error")
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
