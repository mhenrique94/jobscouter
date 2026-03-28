from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from jobscouter.api.routes.config import router as config_router
from jobscouter.api.routes.control import router as control_router
from jobscouter.api.routes.jobs import router as jobs_router
from jobscouter.core.logging import get_logger
from jobscouter.db.session import engine
from jobscouter.services.filter import FilterConfigService

logger = get_logger("jobscouter.api.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        with Session(engine) as session:
            service = FilterConfigService(session)
            service.seed_if_empty()
            session.commit()
    except Exception as exc:
        logger.exception("Falha ao executar seed inicial de configuracao: %s", exc)
    yield


app = FastAPI(title="JobScouter API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router, prefix="/api/v1")
app.include_router(control_router, prefix="/api/v1/control")
app.include_router(config_router, prefix="/api/v1")


if __name__ == "__main__":
    uvicorn.run("jobscouter.api.main:app", host="0.0.0.0", port=8000)
