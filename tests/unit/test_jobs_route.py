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


def _seed_custom_jobs(engine) -> None:
    now = datetime.now(UTC)
    fixtures = [
        {
            "title": "Analyzed High Recent",
            "status": JobStatus.analyzed,
            "ai_score": 9,
            "created_offset_minutes": 6,
        },
        {
            "title": "Analyzed High Older",
            "status": JobStatus.analyzed,
            "ai_score": 9,
            "created_offset_minutes": 4,
        },
        {
            "title": "Analyzed Low",
            "status": JobStatus.analyzed,
            "ai_score": 4,
            "created_offset_minutes": 5,
        },
        {
            "title": "Ready For AI",
            "status": JobStatus.ready_for_ai,
            "ai_score": None,
            "created_offset_minutes": 7,
        },
        {
            "title": "Pending Review",
            "status": JobStatus.pending,
            "ai_score": None,
            "created_offset_minutes": 8,
        },
        {
            "title": "Discarded Candidate",
            "status": JobStatus.discarded,
            "ai_score": 2,
            "created_offset_minutes": 9,
        },
    ]

    with Session(engine) as session:
        for index, fixture in enumerate(fixtures, start=1):
            created_at = now + timedelta(minutes=fixture["created_offset_minutes"])
            session.add(
                Job(
                    title=fixture["title"],
                    company="Acme",
                    url=f"https://example.com/custom/{index}",
                    source="remoteok",
                    description_raw="descricao",
                    status=fixture["status"],
                    ai_score=fixture["ai_score"],
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
    assert payload["items"][0]["title"] == "Job 14"


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


def test_list_jobs_supports_multiple_status_filters() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    _seed_custom_jobs(engine)

    app = _build_app(engine)
    client = TestClient(app)

    response = client.get("/api/v1/jobs?status=analyzed&status=ready_for_ai&page=1&size=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 4
    assert [item["title"] for item in payload["items"]] == [
        "Analyzed High Recent",
        "Analyzed High Older",
        "Analyzed Low",
        "Ready For AI",
    ]


def test_list_jobs_supports_score_range_and_excluded_status() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    _seed_custom_jobs(engine)

    app = _build_app(engine)
    client = TestClient(app)

    response = client.get(
        "/api/v1/jobs",
        params={
            "min_score": 0,
            "max_score": 6,
            "exclude_status": "discarded",
            "page": 1,
            "size": 10,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["title"] for item in payload["items"]] == ["Analyzed Low"]


def test_list_jobs_orders_by_score_then_created_at_desc() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    _seed_custom_jobs(engine)

    app = _build_app(engine)
    client = TestClient(app)

    response = client.get("/api/v1/jobs", params={"page": 1, "size": 10})

    assert response.status_code == 200
    payload = response.json()
    assert [item["title"] for item in payload["items"]] == [
        "Analyzed High Recent",
        "Analyzed High Older",
        "Analyzed Low",
        "Discarded Candidate",
        "Pending Review",
        "Ready For AI",
    ]


def test_list_jobs_rejects_invalid_status() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    app = _build_app(engine)
    client = TestClient(app)

    response = client.get("/api/v1/jobs", params=[("status", "invalid")])

    assert response.status_code == 422
    assert "Invalid status 'invalid'" in response.json()["detail"]


def test_list_jobs_rejects_invalid_excluded_status() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    app = _build_app(engine)
    client = TestClient(app)

    response = client.get("/api/v1/jobs", params=[("exclude_status", "invalid")])

    assert response.status_code == 422
    assert "Invalid exclude_status 'invalid'" in response.json()["detail"]


def test_list_jobs_rejects_invalid_score_range() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    app = _build_app(engine)
    client = TestClient(app)

    response = client.get("/api/v1/jobs", params={"min_score": 8, "max_score": 6})

    assert response.status_code == 422
    assert "min_score cannot be greater than max_score" in response.json()["detail"]


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
