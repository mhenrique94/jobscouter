from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, col, select

from jobscouter.api.deps import get_session
from jobscouter.db.models import Job, JobStatus
from jobscouter.schemas.job import PaginatedJobsResponse

router = APIRouter(tags=["jobs"])


@router.get(
    "/jobs",
    response_model=PaginatedJobsResponse,
    summary="Listar vagas",
    description=(
        "Retorna vagas persistidas com filtros opcionais por status e score minimo de IA. "
        "Use para explorar rapidamente o pipeline de ingestao e analise."
    ),
    response_description="Lista paginada de vagas encontradas.",
)
def list_jobs(
    session: Annotated[Session, Depends(get_session)],
    status: str | None = Query(
        default=None, description="Filtra por status (pending, ready_for_ai, discarded, analyzed)."
    ),
    min_score: int | None = Query(
        default=None, description="Filtra vagas com ai_score maior ou igual ao valor informado."
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

    if status is not None:
        try:
            status_value = JobStatus(status)
        except ValueError as exc:
            valid_values = ", ".join(item.value for item in JobStatus)
            raise HTTPException(
                status_code=422, detail=f"Invalid status '{status}'. Valid values: {valid_values}"
            ) from exc
        statement = statement.where(Job.status == status_value)

    if min_score is not None:
        statement = statement.where(col(Job.ai_score).is_not(None)).where(
            col(Job.ai_score) >= min_score
        )

    total_statement = select(func.count()).select_from(statement.subquery())
    total = int(session.exec(total_statement).one())

    offset = (page - 1) * size
    items_statement = (
        statement.order_by(col(Job.created_at).desc(), col(Job.id).desc())
        .offset(offset)
        .limit(size)
    )
    items = list(session.exec(items_statement).all())

    return PaginatedJobsResponse(items=items, total=total, page=page, size=size)
