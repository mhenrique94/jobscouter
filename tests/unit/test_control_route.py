from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import jobscouter.api.routes.control as control_route
from jobscouter.api.deps import get_session
from jobscouter.db.models import Job, JobStatus


@dataclass
class _FakeAnalysisResult:
    score: int
    summary: str


class _FakeAIAnalyzerService:
    def __init__(self, session: Session) -> None:
        _ = session

    async def analyze_job(self, job: Job) -> _FakeAnalysisResult:
        return _FakeAnalysisResult(score=9, summary=f"Resumo teste para vaga {job.id}")


def _build_app(engine):
    app = FastAPI()
    app.include_router(control_route.router, prefix="/api/v1/control")

    def _override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    return app


def _seed_job(engine, *, status: JobStatus = JobStatus.ready_for_ai) -> Job:
    with Session(engine) as session:
        job = Job(
            title="Python Developer",
            company="Acme",
            url="https://example.com/job",
            source="remoteok",
            description_raw="descricao",
            status=status,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job


def test_analyze_job_returns_updated_job(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    job = _seed_job(engine, status=JobStatus.ready_for_ai)
    monkeypatch.setattr(control_route, "AIAnalyzerService", _FakeAIAnalyzerService)

    app = _build_app(engine)
    client = TestClient(app)

    response = client.post(f"/api/v1/control/analyze/{job.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == job.id
    assert payload["status"] == "analyzed"
    assert payload["ai_score"] == 9
    assert payload["ai_summary"] == f"Resumo teste para vaga {job.id}"


def test_analyze_job_returns_404_for_unknown_job(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    monkeypatch.setattr(control_route, "AIAnalyzerService", _FakeAIAnalyzerService)

    app = _build_app(engine)
    client = TestClient(app)

    response = client.post("/api/v1/control/analyze/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Vaga nao encontrada."


def test_analyze_job_returns_422_for_discarded_job(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    job = _seed_job(engine, status=JobStatus.discarded)
    monkeypatch.setattr(control_route, "AIAnalyzerService", _FakeAIAnalyzerService)

    app = _build_app(engine)
    client = TestClient(app)

    response = client.post(f"/api/v1/control/analyze/{job.id}")

    assert response.status_code == 422
    assert (
        response.json()["detail"] == "Vagas descartadas nao podem ser analisadas individualmente."
    )
