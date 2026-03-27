from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, select

from jobscouter.api.deps import get_session
from jobscouter.db.models import Job, JobStatus


router = APIRouter(tags=["jobs"])


@router.get(
    "/jobs",
    response_model=list[Job],
    summary="Listar vagas",
    description=(
        "Retorna vagas persistidas com filtros opcionais por status e score minimo de IA. "
        "Use para explorar rapidamente o pipeline de ingestao e analise."
    ),
    response_description="Lista de vagas encontradas.",
)
def list_jobs(
    session: Annotated[Session, Depends(get_session)],
    status: str | None = Query(default=None, description="Filtra por status (pending, ready_for_ai, discarded, analyzed)."),
    min_score: int | None = Query(default=None, description="Filtra vagas com ai_score maior ou igual ao valor informado."),
    limit: int = Query(default=20, ge=1, description="Quantidade maxima de vagas retornadas."),
) -> list[Job]:
    statement = select(Job)

    if status is not None:
        try:
            status_value = JobStatus(status)
        except ValueError as exc:
            valid_values = ", ".join(item.value for item in JobStatus)
            raise HTTPException(status_code=422, detail=f"Invalid status '{status}'. Valid values: {valid_values}") from exc
        statement = statement.where(Job.status == status_value)

    if min_score is not None:
        statement = statement.where(col(Job.ai_score).is_not(None)).where(col(Job.ai_score) >= min_score)

    statement = statement.limit(limit)
    return list(session.exec(statement).all())
