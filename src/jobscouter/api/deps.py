from __future__ import annotations

from collections.abc import Generator

from sqlmodel import Session

from jobscouter.db.session import engine


def get_session() -> Generator[Session, None, None]:
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
