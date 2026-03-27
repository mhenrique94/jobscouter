from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from jobscouter.core.config import get_settings


settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
