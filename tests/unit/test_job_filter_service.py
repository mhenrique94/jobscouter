from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

from jobscouter.db.models import FilterConfig, Job, JobStatus
from jobscouter.services.filter import JobFilterService, validate_job_assertiveness


def _build_job(title: str, description_raw: str, status: JobStatus = JobStatus.pending) -> Job:
    now = datetime.now(UTC)
    return Job(
        external_id="ext-1",
        title=title,
        company="Acme",
        url="https://example.com/job/1",
        source="remoteok",
        description_raw=description_raw,
        location="Remote",
        salary=None,
        status=status,
        filter_reason=None,
        created_at=now,
        first_seen_at=now,
        last_seen_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_discarded_when_contains_exclude_keyword(tmp_path) -> None:
    filters_path = tmp_path / "filters.yaml"
    filters_path.write_text(
        """
filters:
  exclude_keywords: [\"Presencial\"]
  include_keywords: [\"Python\"]
""".strip(),
        encoding="utf-8",
    )

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        job = _build_job("Desenvolvedor Python", "Vaga 100% presencial")
        session.add(job)
        session.flush()

        service = JobFilterService(session, filters_path=filters_path)
        result = await service.classify_job(job)

        assert result == JobStatus.discarded
        assert job.status == JobStatus.discarded
        assert job.filter_reason == "Palavra excluida: Presencial"


@pytest.mark.asyncio
async def test_ready_for_ai_when_contains_include_keyword(tmp_path) -> None:
    filters_path = tmp_path / "filters.yaml"
    filters_path.write_text(
        """
filters:
  exclude_keywords: [\"Presencial\"]
  include_keywords: [\"Python\"]
""".strip(),
        encoding="utf-8",
    )

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        job = _build_job("Engenheiro Backend", "Atuacao com Python e APIs")
        session.add(job)
        session.flush()

        service = JobFilterService(session, filters_path=filters_path)
        result = await service.classify_job(job)

        assert result == JobStatus.ready_for_ai
        assert job.status == JobStatus.ready_for_ai
        assert job.filter_reason is None


def test_assertiveness_retorna_true_quando_threshold_atingido() -> None:
    keywords = {"python", "fastapi", "django", "postgresql"}
    content = "Backend Engineer com Python, FastAPI e Django"
    is_assertive, count = validate_job_assertiveness(content, keywords)
    assert is_assertive is True
    assert count == 3


def test_assertiveness_retorna_false_quando_abaixo_do_threshold() -> None:
    keywords = {"python", "fastapi", "django"}
    content = "Backend Engineer com Python apenas"
    is_assertive, count = validate_job_assertiveness(content, keywords, threshold=3)
    assert is_assertive is False
    assert count == 1


def test_assertiveness_e_case_insensitive() -> None:
    keywords = {"python", "fastapi"}
    content = "Engenheiro com PYTHON e FASTAPI"
    is_assertive, count = validate_job_assertiveness(content, keywords, threshold=2)
    assert is_assertive is True
    assert count == 2


def test_assertiveness_com_keywords_vazias_desabilita_validacao() -> None:
    # keywords vazio significa "validação desabilitada" — não deve descartar nenhuma vaga
    is_assertive, count = validate_job_assertiveness("Qualquer conteudo", set())
    assert is_assertive is True
    assert count == 0


@pytest.mark.asyncio
async def test_pending_when_matches_no_keywords(tmp_path) -> None:
    filters_path = tmp_path / "filters.yaml"
    filters_path.write_text(
        """
filters:
  exclude_keywords: [\"PHP\"]
  include_keywords: [\"Django\"]
""".strip(),
        encoding="utf-8",
    )

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        job = _build_job("Software Engineer", "Stack diversa sem termos de filtro")
        session.add(job)
        session.flush()

        service = JobFilterService(session, filters_path=filters_path)
        result = await service.classify_job(job)

        assert result == JobStatus.pending
        assert job.status == JobStatus.pending
        assert job.filter_reason is None


@pytest.mark.asyncio
async def test_exclude_has_priority_over_include(tmp_path) -> None:
    filters_path = tmp_path / "filters.yaml"
    filters_path.write_text(
        """
filters:
  exclude_keywords: [\"Java\"]
  include_keywords: [\"Python\"]
""".strip(),
        encoding="utf-8",
    )

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        job = _build_job("Dev Python", "Projeto com migracao de Java para Python")
        session.add(job)
        session.flush()

        service = JobFilterService(session, filters_path=filters_path)
        result = await service.classify_job(job)

        assert result == JobStatus.discarded
        assert job.status == JobStatus.discarded


@pytest.mark.asyncio
async def test_case_insensitive_matching(tmp_path) -> None:
    filters_path = tmp_path / "filters.yaml"
    filters_path.write_text(
        """
filters:
  exclude_keywords: [\"Híbrido\"]
  include_keywords: [\"Home Office\"]
""".strip(),
        encoding="utf-8",
    )

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        job = _build_job("Desenvolvedor", "Modelo HÍBRIDO com alguns dias em Home office")
        session.add(job)
        session.flush()

        service = JobFilterService(session, filters_path=filters_path)
        result = await service.classify_job(job)

        assert result == JobStatus.discarded


@pytest.mark.asyncio
async def test_analyzed_status_is_preserved(tmp_path) -> None:
    filters_path = tmp_path / "filters.yaml"
    filters_path.write_text(
        """
filters:
  exclude_keywords: [\"Presencial\"]
  include_keywords: [\"Python\"]
""".strip(),
        encoding="utf-8",
    )

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        job = _build_job("Dev Python", "Vaga presencial", status=JobStatus.analyzed)
        session.add(job)
        session.flush()

        service = JobFilterService(session, filters_path=filters_path)
        result = await service.classify_job(job)

        assert result == JobStatus.analyzed
        assert job.status == JobStatus.analyzed
        assert job.filter_reason is None


@pytest.mark.asyncio
async def test_database_rules_have_priority_over_yaml(tmp_path) -> None:
    filters_path = tmp_path / "filters.yaml"
    filters_path.write_text(
        """
filters:
  exclude_keywords: ["Python"]
  include_keywords: ["Java"]
""".strip(),
        encoding="utf-8",
    )

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            FilterConfig(
                id=1,
                search_terms=["python"],
                exclude_keywords=["Java"],
                include_keywords=["Python"],
            )
        )
        session.flush()

        job = _build_job("Desenvolvedor", "Atuacao com Python")
        session.add(job)
        session.flush()

        service = JobFilterService(session, filters_path=filters_path)
        result = await service.classify_job(job)

        assert result == JobStatus.ready_for_ai
        assert job.status == JobStatus.ready_for_ai
        assert job.filter_reason is None
