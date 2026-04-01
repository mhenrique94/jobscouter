from __future__ import annotations

import dataclasses

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import jobscouter.api.routes.control as control_route
from jobscouter.api.deps import get_session
from jobscouter.core.config import Settings
from jobscouter.db.models import Job, JobStatus

_BASE_SETTINGS = Settings(
    database_url="sqlite://",
    log_level="INFO",
    request_timeout=10.0,
    remoteok_api_url="https://remoteok.com/api",
    remotar_base_url="https://remotar.com.br",
    remotar_api_url="https://api.remotar.com.br",
    user_agent="test-bot/0.1",
    gemini_api_key="fake-key",
    gemini_model="models/gemini-2.5-flash-lite",
    gemini_retry_delay_seconds=1.0,
    app_env="development",
)


_PROD_SETTINGS = dataclasses.replace(_BASE_SETTINGS, app_env="production")


@dataclasses.dataclass
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


def test_get_logs_returns_403_in_production(monkeypatch) -> None:
    monkeypatch.setattr(control_route, "get_settings", lambda: _PROD_SETTINGS)
    app = FastAPI()
    app.include_router(control_route.router, prefix="/api/v1/control")
    client = TestClient(app)

    response = client.get("/api/v1/control/logs")

    assert response.status_code == 403
    assert "producao" in response.json()["detail"]


def test_get_logs_redacts_sensitive_data(monkeypatch) -> None:
    monkeypatch.setattr(control_route, "get_settings", lambda: _BASE_SETTINGS)
    sensitive_lines = [
        "postgresql+psycopg://user:s3cr3t@localhost/db",
        "gemini_api_key=AIzaSyABC123xyz",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.token",
    ]
    monkeypatch.setattr(control_route, "read_log_lines", lambda n: sensitive_lines)

    app = FastAPI()
    app.include_router(control_route.router, prefix="/api/v1/control")
    client = TestClient(app)

    response = client.get("/api/v1/control/logs")

    assert response.status_code == 200
    body = "\n".join(response.json()["lines"])
    assert "s3cr3t" not in body
    assert "AIzaSyABC123xyz" not in body
    assert "eyJhbGciOiJIUzI1NiJ9.token" not in body
    assert "***" in body


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


def test_update_job_status_ready_for_ai(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    job = _seed_job(engine, status=JobStatus.pending)
    app = _build_app(engine)
    client = TestClient(app)

    response = client.patch(
        f"/api/v1/control/jobs/{job.id}/status",
        json={"status": "ready_for_ai"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == job.id
    assert payload["status"] == "ready_for_ai"


def test_update_job_status_discarded(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    job = _seed_job(engine, status=JobStatus.pending)
    app = _build_app(engine)
    client = TestClient(app)

    response = client.patch(
        f"/api/v1/control/jobs/{job.id}/status",
        json={"status": "discarded"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == job.id
    assert payload["status"] == "discarded"


def test_update_job_status_invalid_status(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    job = _seed_job(engine, status=JobStatus.pending)
    app = _build_app(engine)
    client = TestClient(app)

    response = client.patch(
        f"/api/v1/control/jobs/{job.id}/status",
        json={"status": "analyzed"},
    )
    assert response.status_code == 422
    assert "status" in str(response.json()["detail"]).lower()


def test_update_job_status_not_found(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    app = _build_app(engine)
    client = TestClient(app)

    response = client.patch(
        "/api/v1/control/jobs/999/status",
        json={"status": "ready_for_ai"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Vaga nao encontrada."
