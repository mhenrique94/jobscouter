from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from jobscouter.api.deps import get_session
from jobscouter.schemas.config import FilterConfigPatchRequest, FilterConfigResponse
from jobscouter.services.filter import FilterConfigService

router = APIRouter(tags=["config"])


@router.get(
    "/config",
    response_model=FilterConfigResponse,
    summary="Obter configuracao de filtros",
    description=(
        "Retorna a configuracao ativa usada no sistema (search_terms, include_keywords e exclude_keywords). "
        "Prioriza dados do banco e aplica fallback para YAML quando necessario."
    ),
    response_description="Configuracao atual de filtros.",
)
def get_config(session: Annotated[Session, Depends(get_session)]) -> FilterConfigResponse:
    service = FilterConfigService(session)
    config = service.get_active_config()
    return FilterConfigResponse(
        search_terms=list(config.search_terms),
        include_keywords=list(config.include_keywords),
        exclude_keywords=list(config.exclude_keywords),
    )


@router.patch(
    "/config",
    response_model=FilterConfigResponse,
    summary="Atualizar configuracao de filtros",
    description=(
        "Atualiza parcialmente a configuracao ativa. "
        "Envie apenas os campos que deseja alterar; os demais permanecem inalterados."
    ),
    response_description="Configuracao atualizada de filtros.",
)
def patch_config(
    payload: FilterConfigPatchRequest,
    session: Annotated[Session, Depends(get_session)],
) -> FilterConfigResponse:
    service = FilterConfigService(session)
    model = service.update_active(
        search_terms=payload.search_terms,
        include_keywords=payload.include_keywords,
        exclude_keywords=payload.exclude_keywords,
    )
    session.commit()
    session.refresh(model)
    return FilterConfigResponse(
        search_terms=list(model.search_terms),
        include_keywords=list(model.include_keywords),
        exclude_keywords=list(model.exclude_keywords),
    )
