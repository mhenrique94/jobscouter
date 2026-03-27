from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from jobscouter.api.deps import get_session
from jobscouter.api.routes.config import router
from jobscouter.db.models import FilterConfig


def _build_app(engine):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def _override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    return app


def test_get_config_returns_database_values() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            FilterConfig(
                id=1,
                search_terms=["python", "django"],
                include_keywords=["Remote"],
                exclude_keywords=["Presencial"],
            )
        )
        session.commit()

    app = _build_app(engine)
    client = TestClient(app)

    response = client.get("/api/v1/config")

    assert response.status_code == 200
    assert response.json() == {
        "search_terms": ["python", "django"],
        "include_keywords": ["Remote"],
        "exclude_keywords": ["Presencial"],
    }


def test_patch_config_updates_keywords() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            FilterConfig(
                id=1,
                search_terms=["python"],
                include_keywords=["Remote"],
                exclude_keywords=["Presencial"],
            )
        )
        session.commit()

    app = _build_app(engine)
    client = TestClient(app)

    response = client.patch(
        "/api/v1/config",
        json={
            "search_terms": ["python", "vue"],
            "include_keywords": ["Remoto", "Django"],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "search_terms": ["python", "vue"],
        "include_keywords": ["Remoto", "Django"],
        "exclude_keywords": ["Presencial"],
    }
