from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlmodel import Session, SQLModel, create_engine

from jobscouter.core.config import Settings
from jobscouter.db.models import FilterConfig, Job, JobStatus
from jobscouter.services import analyzer
from jobscouter.services.analyzer import AIAnalyzerService


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModel:
    def __init__(self, texts: list[str] | None = None, exception: Exception | None = None) -> None:
        self.texts = texts or []
        self.exception = exception
        self.calls = 0

    def generate_content(self, *_args, **_kwargs):
        self.calls += 1
        if self.exception is not None and self.calls == 1:
            raise self.exception
        if self.texts:
            return _FakeResponse(self.texts[min(self.calls - 1, len(self.texts) - 1)])
        return _FakeResponse('{"score": 7, "summary": "match"}')


class _FakeResourceExhausted(Exception):
    pass


class _FakeNotFound(Exception):
    pass


class _AlwaysResourceExhaustedModel:
    def generate_content(self, *_args, **_kwargs):
        raise _FakeResourceExhausted("quota exceeded")


class _SuccessModel:
    def __init__(self, text: str = '{"score": 4, "summary": "Fallback funcionou"}') -> None:
        self.text = text

    def generate_content(self, *_args, **_kwargs):
        return _FakeResponse(self.text)


def _settings() -> Settings:
    return Settings(
        database_url="sqlite://",
        log_level="INFO",
        request_timeout=10.0,
        remoteok_api_url="https://remoteok.com/api",
        remotar_base_url="https://remotar.com.br",
        remotar_api_url="https://api.remotar.com.br",
        user_agent="test-agent",
        gemini_api_key="test-key",
        gemini_model="models/gemini-2.5-flash-lite",
        gemini_retry_delay_seconds=0.01,
    )


def _build_job(title: str, description_raw: str) -> Job:
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
        status=JobStatus.ready_for_ai,
        filter_reason=None,
        created_at=now,
        first_seen_at=now,
        last_seen_at=now,
        updated_at=now,
    )


def _configure_fake_google_modules(monkeypatch, fake_model: _FakeModel) -> None:
    fake_genai = SimpleNamespace(
        configure=lambda **_kwargs: None,
        GenerativeModel=lambda _name: fake_model,
        GenerationConfig=lambda **kwargs: kwargs,
        list_models=lambda: [],
    )
    fake_api_exceptions = SimpleNamespace(
        ResourceExhausted=_FakeResourceExhausted, NotFound=_FakeNotFound
    )

    def _fake_import_module(name: str):
        if name == "google.generativeai":
            return fake_genai
        if name == "google.api_core.exceptions":
            return fake_api_exceptions
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(analyzer.importlib, "import_module", _fake_import_module)


@pytest.mark.asyncio
async def test_non_dev_job_returns_zero_without_model_call(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    fake_model = _FakeModel()
    _configure_fake_google_modules(monkeypatch, fake_model)

    with Session(engine) as session:
        service = AIAnalyzerService(session, settings=_settings())
        result = await service.analyze_job(_build_job("Contador Senior", "Rotinas contabeis"))

    assert result.score == 0
    assert "fora de desenvolvimento" in result.summary
    assert fake_model.calls == 0


@pytest.mark.asyncio
async def test_non_dev_keyword_does_not_match_inside_other_words(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    fake_model = _FakeModel(texts=['{"score": 8, "summary": "Boa aderencia"}'])
    _configure_fake_google_modules(monkeypatch, fake_model)

    with Session(engine) as session:
        service = AIAnalyzerService(session, settings=_settings())
        result = await service.analyze_job(
            _build_job(
                "Backend Developer",
                "Company acquired recently. Strong Linux knowledge and cloud experience.",
            )
        )

    assert result.score == 8
    assert result.summary == "Boa aderencia"
    assert fake_model.calls == 1


@pytest.mark.asyncio
async def test_non_dev_keyword_still_matches_full_word(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    fake_model = _FakeModel()
    _configure_fake_google_modules(monkeypatch, fake_model)

    with Session(engine) as session:
        service = AIAnalyzerService(session, settings=_settings())
        result = await service.analyze_job(
            _build_job("Product Designer", "Colaboracao com time de UX e UI")
        )

    assert result.score == 0
    assert "fora de desenvolvimento" in result.summary
    assert fake_model.calls == 0


def test_build_prompt_includes_filter_keywords_from_yaml(monkeypatch, tmp_path) -> None:
    filters_path = tmp_path / "filters.yaml"
    filters_path.write_text(
        """
filters:
  exclude_keywords: ["Presencial", "Java"]
  include_keywords: ["Python", "Django", "Vue"]
""".strip(),
        encoding="utf-8",
    )

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    fake_model = _FakeModel()
    _configure_fake_google_modules(monkeypatch, fake_model)

    with Session(engine) as session:
        service = AIAnalyzerService(session, settings=_settings(), filters_path=filters_path)
        prompt = service._build_prompt(_build_job("Backend Developer", "Atuacao com APIs"))

    assert "TECNOLOGIAS DESEJADAS (CORE STACK): Python, Django, Vue" in prompt
    assert "TECNOLOGIAS/TERMOS A EVITAR: Presencial, Java" in prompt
    assert "LOCALIZACAO DO CANDIDATO: Brasil" in prompt
    assert "REGRAS DE VETO DE LOCALIZACAO (prioridade maxima):" in prompt
    assert "remota e restrita ao Brasil/Brazil, ela e elegivel" in prompt
    assert "remota e restrita a LATAM/America Latina, ela e elegivel" in prompt
    assert "Remote Global/Worldwide/Anywhere, ela e elegivel" in prompt
    assert "[VETO - Localizacao]" in prompt
    assert "REGRAS DE VETO DE FUNCAO:" in prompt
    assert "Software Development / Engineering" in prompt
    assert (
        "PASSO 1 - Liste quais include_keywords (Python, Django, Vue) aparecem LITERALMENTE"
        in prompt
    )
    assert '"score"' in prompt and '"summary"' in prompt


def test_build_prompt_prioritizes_database_filter_config(monkeypatch, tmp_path) -> None:
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

    fake_model = _FakeModel()
    _configure_fake_google_modules(monkeypatch, fake_model)

    with Session(engine) as session:
        session.add(
            FilterConfig(
                id=1,
                search_terms=["python"],
                exclude_keywords=["Java"],
                include_keywords=["Python", "Django"],
            )
        )
        session.flush()

        service = AIAnalyzerService(session, settings=_settings(), filters_path=filters_path)
        prompt = service._build_prompt(_build_job("Backend Developer", "Atuacao com APIs"))

    assert "TECNOLOGIAS DESEJADAS (CORE STACK): Python, Django" in prompt
    assert "TECNOLOGIAS/TERMOS A EVITAR: Java" in prompt


@pytest.mark.asyncio
async def test_non_dev_correlated_role_returns_zero_without_model_call(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    fake_model = _FakeModel()
    _configure_fake_google_modules(monkeypatch, fake_model)

    with Session(engine) as session:
        service = AIAnalyzerService(session, settings=_settings())
        result = await service.analyze_job(
            _build_job("Data Scientist", "Modelagem estatistica e experimentos")
        )

    assert result.score == 0
    assert "fora de desenvolvimento" in result.summary
    assert fake_model.calls == 0


@pytest.mark.asyncio
async def test_data_science_in_description_does_not_block_dev_role(monkeypatch) -> None:
    """Vaga de dev cujo título não menciona data science não deve ser barrada
    apenas porque a descrição da empresa faz referência contextual ao termo."""
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    fake_model = _FakeModel(texts=['{"score": 8, "summary": "Boa aderencia"}'])
    _configure_fake_google_modules(monkeypatch, fake_model)

    with Session(engine) as session:
        service = AIAnalyzerService(session, settings=_settings())
        result = await service.analyze_job(
            _build_job(
                "Fullstack Software Engineer Core",
                "Our platform connects many data science technologies and tools.",
            )
        )

    assert result.score == 8
    assert fake_model.calls == 1


@pytest.mark.asyncio
async def test_data_science_in_title_still_blocks_job(monkeypatch) -> None:
    """Vaga com 'data science' no título ainda deve ser barrada."""
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    fake_model = _FakeModel()
    _configure_fake_google_modules(monkeypatch, fake_model)

    with Session(engine) as session:
        service = AIAnalyzerService(session, settings=_settings())
        result = await service.analyze_job(
            _build_job("Data Science Engineer", "Modelagem e experimentos em larga escala.")
        )

    assert result.score == 0
    assert "fora de desenvolvimento" in result.summary
    assert fake_model.calls == 0


@pytest.mark.asyncio
async def test_non_dev_sales_keyword_does_not_match_inside_salesforce(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    fake_model = _FakeModel(texts=['{"score": 7, "summary": "Boa aderencia"}'])
    _configure_fake_google_modules(monkeypatch, fake_model)

    with Session(engine) as session:
        service = AIAnalyzerService(session, settings=_settings())
        result = await service.analyze_job(
            _build_job("Backend Engineer", "Integracao com Salesforce e APIs Python")
        )

    assert result.score == 7
    assert result.summary == "Boa aderencia"
    assert fake_model.calls == 1


@pytest.mark.asyncio
async def test_analyze_job_parses_json_and_clamps_score(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    fake_model = _FakeModel(texts=['{"score": 12, "summary": "Muito aderente"}'])
    _configure_fake_google_modules(monkeypatch, fake_model)

    with Session(engine) as session:
        service = AIAnalyzerService(session, settings=_settings())
        result = await service.analyze_job(
            _build_job("Full-stack Developer", "Python Django e Vue.js")
        )

    assert result.score == 10
    assert result.summary == "Muito aderente"
    assert fake_model.calls == 1


@pytest.mark.asyncio
async def test_analyze_job_retries_on_resource_exhausted(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    fake_model = _FakeModel(
        texts=['{"score": 6, "summary": "Boa aderencia"}'],
        exception=_FakeResourceExhausted("rate limited"),
    )
    _configure_fake_google_modules(monkeypatch, fake_model)

    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(analyzer.asyncio, "sleep", _fake_sleep)

    with Session(engine) as session:
        service = AIAnalyzerService(session, settings=_settings())
        result = await service.analyze_job(_build_job("Backend Python", "APIs em Django"))

    assert result.score == 6
    assert result.summary == "Boa aderencia"
    assert fake_model.calls == 2
    assert sleep_calls


@pytest.mark.asyncio
async def test_switches_model_when_resource_exhausted(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    created_models: list[str] = []

    def _model_factory(name: str):
        created_models.append(name)
        if len(created_models) == 1:
            return _AlwaysResourceExhaustedModel()
        return _SuccessModel('{"score": 5, "summary": "Usou fallback de modelo"}')

    fake_genai = SimpleNamespace(
        configure=lambda **_kwargs: None,
        GenerativeModel=_model_factory,
        GenerationConfig=lambda **kwargs: kwargs,
        list_models=lambda: [],
    )
    fake_api_exceptions = SimpleNamespace(
        ResourceExhausted=_FakeResourceExhausted, NotFound=_FakeNotFound
    )

    def _fake_import_module(name: str):
        if name == "google.generativeai":
            return fake_genai
        if name == "google.api_core.exceptions":
            return fake_api_exceptions
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(analyzer.importlib, "import_module", _fake_import_module)

    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(analyzer.asyncio, "sleep", _fake_sleep)

    with Session(engine) as session:
        service = AIAnalyzerService(session, settings=_settings())
        result = await service.analyze_job(_build_job("Backend Python", "APIs"))

    assert result.score == 5
    assert result.summary == "Usou fallback de modelo"
    assert len(created_models) >= 2
    assert sleep_calls


@pytest.mark.asyncio
async def test_high_growth_context_does_not_trigger_non_dev_classification(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    fake_model = _FakeModel(texts=['{"score": 8, "summary": "Boa aderencia"}'])
    _configure_fake_google_modules(monkeypatch, fake_model)

    with Session(engine) as session:
        service = AIAnalyzerService(session, settings=_settings())
        result = await service.analyze_job(
            _build_job(
                "Senior Full Stack Software Engineer",
                "We work in high-growth environments and ship features weekly.",
            )
        )

    assert result.score == 8
    assert fake_model.calls == 1


@pytest.mark.asyncio
async def test_non_dev_summary_includes_triggering_keyword(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    fake_model = _FakeModel()
    _configure_fake_google_modules(monkeypatch, fake_model)

    with Session(engine) as session:
        service = AIAnalyzerService(session, settings=_settings())
        result = await service.analyze_job(
            _build_job("Growth Hacker", "Estrategias de aquisicao e retencao de usuarios.")
        )

    assert result.score == 0
    assert "fora de desenvolvimento" in result.summary
    assert "'growth hacker'" in result.summary
    assert fake_model.calls == 0


def test_build_prompt_includes_level_rules_when_level_in_keywords(monkeypatch, tmp_path) -> None:
    filters_path = tmp_path / "filters.yaml"
    filters_path.write_text(
        """
filters:
  exclude_keywords: ["Junior"]
  include_keywords: ["Python", "Django", "Senior"]
""".strip(),
        encoding="utf-8",
    )
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    fake_model = _FakeModel()
    _configure_fake_google_modules(monkeypatch, fake_model)

    with Session(engine) as session:
        service = AIAnalyzerService(session, settings=_settings(), filters_path=filters_path)
        prompt = service._build_prompt(_build_job("Backend Developer", "Python, Django, Remote"))

    assert "REGRAS DE NIVEL" in prompt
    assert "Nivel-alvo do candidato: Senior" in prompt
    assert "Junior < Pleno < Senior" in prompt
    assert "[VETO - Nivel]" in prompt


def test_build_prompt_omits_level_rules_when_no_level_in_keywords(monkeypatch, tmp_path) -> None:
    filters_path = tmp_path / "filters.yaml"
    filters_path.write_text(
        """
filters:
  exclude_keywords: ["Java"]
  include_keywords: ["Python", "Django", "Vue"]
""".strip(),
        encoding="utf-8",
    )
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    fake_model = _FakeModel()
    _configure_fake_google_modules(monkeypatch, fake_model)

    with Session(engine) as session:
        service = AIAnalyzerService(session, settings=_settings(), filters_path=filters_path)
        prompt = service._build_prompt(_build_job("Backend Developer", "Python, Django, Remote"))

    assert "REGRAS DE NIVEL" not in prompt
