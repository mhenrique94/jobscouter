from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from jobscouter.api.deps import get_session
from jobscouter.api.routes.jobs import router
from jobscouter.db.models import Job, JobStatus


def _build_app(engine):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def _override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    return app


def _seed_jobs(engine, total: int = 55) -> None:
    now = datetime.now(UTC)
    with Session(engine) as session:
        for index in range(1, total + 1):
            created_at = now + timedelta(minutes=index)
            status = JobStatus.analyzed if index % 2 == 0 else JobStatus.pending
            ai_score = 8 if status is JobStatus.analyzed else None
            session.add(
                Job(
                    title=f"Job {index}",
                    company="Acme",
                    url=f"https://example.com/jobs/{index}",
                    source="remoteok",
                    description_raw="descricao",
                    status=status,
                    ai_score=ai_score,
                    created_at=created_at,
                    first_seen_at=created_at,
                    last_seen_at=created_at,
                    updated_at=created_at,
                )
            )
        session.commit()


def test_list_jobs_returns_paginated_response() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    _seed_jobs(engine)

    app = _build_app(engine)
    client = TestClient(app)

    response = client.get("/api/v1/jobs", params={"page": 2, "size": 20})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 55
    assert payload["page"] == 2
    assert payload["size"] == 20
    assert len(payload["items"]) == 20
    assert payload["items"][0]["title"] == "Job 35"


def test_list_jobs_applies_filters_with_pagination() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    _seed_jobs(engine)

    app = _build_app(engine)
    client = TestClient(app)

    response = client.get(
        "/api/v1/jobs",
        params={"status": "analyzed", "min_score": 8, "page": 1, "size": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 27
    assert payload["page"] == 1
    assert payload["size"] == 10
    assert len(payload["items"]) == 10
    assert all(item["status"] == "analyzed" for item in payload["items"])
    assert all(item["ai_score"] >= 8 for item in payload["items"])


def test_list_jobs_rejects_invalid_status() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    app = _build_app(engine)
    client = TestClient(app)

    response = client.get("/api/v1/jobs", params={"status": "invalid"})

    assert response.status_code == 422
    assert "Invalid status 'invalid'" in response.json()["detail"]


def test_list_jobs_validates_page_and_size() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    app = _build_app(engine)
    client = TestClient(app)

    page_response = client.get("/api/v1/jobs", params={"page": 0})
    assert page_response.status_code == 422

    size_low_response = client.get("/api/v1/jobs", params={"size": 0})
    assert size_low_response.status_code == 422

    size_high_response = client.get("/api/v1/jobs", params={"size": 101})
    assert size_high_response.status_code == 422