from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, col, select

from jobscouter.api.deps import get_session
from jobscouter.db.models import Job, JobStatus
from jobscouter.schemas.job import PaginatedJobsResponse

router = APIRouter(tags=["jobs"])


def _parse_status_filters(raw_statuses: list[str] | None, query_param_name: str) -> list[JobStatus]:
    if not raw_statuses:
        return []

    parsed_statuses: list[JobStatus] = []
    for raw_status in raw_statuses:
        try:
            parsed_statuses.append(JobStatus(raw_status))
        except ValueError as exc:
            valid_values = ", ".join(item.value for item in JobStatus)
            raise HTTPException(
                status_code=422,
                detail=(f"Invalid {query_param_name} '{raw_status}'. Valid values: {valid_values}"),
            ) from exc

    return parsed_statuses


@router.get(
    "/jobs",
    response_model=PaginatedJobsResponse,
    summary="Listar vagas",
    description=(
        "Retorna vagas persistidas com filtros opcionais por status, exclusao de status "
        "e intervalo de score de IA. "
        "Use para explorar rapidamente o pipeline de ingestao e analise."
    ),
    response_description="Lista paginada de vagas encontradas.",
)
def list_jobs(
    session: Annotated[Session, Depends(get_session)],
    status: list[str] | None = Query(
        default=None,
        description=(
            "Filtra por um ou mais status. Repita o parametro para combinar valores "
            "(ex.: status=analyzed&status=ready_for_ai)."
        ),
    ),
    min_score: int | None = Query(
        default=None,
        ge=0,
        le=10,
        description="Filtra vagas com ai_score maior ou igual ao valor informado.",
    ),
    max_score: int | None = Query(
        default=None,
        ge=0,
        le=10,
        description="Filtra vagas com ai_score menor ou igual ao valor informado.",
    ),
    exclude_status: list[str] | None = Query(
        default=None,
        description=(
            "Oculta um ou mais status. Repita o parametro para combinar valores "
            "(ex.: exclude_status=discarded)."
        ),
    ),
    page: int = Query(default=1, ge=1, description="Pagina atual (inicia em 1)."),
    size: int = Query(
        default=50,
        ge=1,
        le=100,
        description="Quantidade de vagas por pagina (maximo 100).",
    ),
) -> PaginatedJobsResponse:
    statement = select(Job)

    status_values = _parse_status_filters(status, "status")
    exclude_status_values = _parse_status_filters(exclude_status, "exclude_status")

    if min_score is not None and max_score is not None and min_score > max_score:
        raise HTTPException(
            status_code=422,
            detail="Invalid score range: min_score cannot be greater than max_score",
        )

    if status_values:
        statement = statement.where(col(Job.status).in_(status_values))

    if exclude_status_values:
        statement = statement.where(col(Job.status).not_in(exclude_status_values))

    if min_score is not None or max_score is not None:
        statement = statement.where(col(Job.ai_score).is_not(None))

    if min_score is not None:
        statement = statement.where(col(Job.ai_score) >= min_score)

    if max_score is not None:
        statement = statement.where(col(Job.ai_score) <= max_score)

    total_statement = statement.with_only_columns(
        func.count(), maintain_column_froms=True
    ).order_by(None)
    total = int(session.exec(total_statement).one())

    offset = (page - 1) * size
    items_statement = (
        statement.order_by(
            col(Job.ai_score).is_(None),
            col(Job.ai_score).desc(),
            col(Job.created_at).desc(),
            col(Job.id).desc(),
        )
        .offset(offset)
        .limit(size)
    )
    items = list(session.exec(items_statement).all())

    return PaginatedJobsResponse(items=items, total=total, page=page, size=size)
