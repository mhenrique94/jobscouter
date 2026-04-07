from __future__ import annotations

from types import SimpleNamespace

import pytest

from jobscouter.core.config import Settings
from jobscouter.services import profile_enricher as enricher_module
from jobscouter.services.profile_enricher import (
    EnrichedProfile,
    ProfileEnricher,
    get_effective_search_terms,
)


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModel:
    def __init__(self, text: str = '{"expanded_keywords": []}') -> None:
        self.response_text = text
        self.calls = 0

    def generate_content(self, *_args, **_kwargs):
        self.calls += 1
        return _FakeResponse(self.response_text)


class _FakeResourceExhausted(Exception):
    pass


class _FakeNotFound(Exception):
    pass


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


def _configure_fake_google(monkeypatch, fake_model: _FakeModel) -> None:
    fake_genai = SimpleNamespace(
        configure=lambda **_kwargs: None,
        GenerativeModel=lambda _name: fake_model,
        GenerationConfig=lambda **kwargs: kwargs,
    )
    fake_exceptions = SimpleNamespace(
        ResourceExhausted=_FakeResourceExhausted,
        NotFound=_FakeNotFound,
    )

    def _fake_import(name: str):
        if name == "google.generativeai":
            return fake_genai
        if name == "google.api_core.exceptions":
            return fake_exceptions
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(enricher_module.importlib, "import_module", _fake_import)


# ---------------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrich_blank_string_returns_empty_profile(monkeypatch) -> None:
    fake_model = _FakeModel()
    _configure_fake_google(monkeypatch, fake_model)

    enricher = ProfileEnricher(settings=_settings())
    result = await enricher.enrich(include_keywords=[""], exclude_keywords=[])

    assert result == EnrichedProfile(original_keywords=(), expanded_keywords=(), added_by_ai=())
    assert fake_model.calls == 0


@pytest.mark.asyncio
async def test_enrich_whitespace_only_terms_returns_empty_profile(monkeypatch) -> None:
    fake_model = _FakeModel()
    _configure_fake_google(monkeypatch, fake_model)

    enricher = ProfileEnricher(settings=_settings())
    result = await enricher.enrich(include_keywords=["  ", "\t"], exclude_keywords=[])

    assert result == EnrichedProfile(original_keywords=(), expanded_keywords=(), added_by_ai=())
    assert fake_model.calls == 0


@pytest.mark.asyncio
async def test_enrich_strips_and_deduplicates_include_keywords(monkeypatch) -> None:
    fake_model = _FakeModel('{"expanded_keywords": []}')
    _configure_fake_google(monkeypatch, fake_model)

    enricher = ProfileEnricher(settings=_settings())
    result = await enricher.enrich(
        include_keywords=["  Python  ", "Python", "django"],
        exclude_keywords=[],
    )

    assert result.original_keywords == ("Python", "django")
    assert fake_model.calls == 1


# ---------------------------------------------------------------------------
# Filtro de exclude_keywords no output da IA
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_enriched_profile_filters_exclude_keywords(monkeypatch) -> None:
    fake_model = _FakeModel('{"expanded_keywords": ["Flask", "Java", "FastAPI"]}')
    _configure_fake_google(monkeypatch, fake_model)

    enricher = ProfileEnricher(settings=_settings())
    result = await enricher.enrich(
        include_keywords=["Python"],
        exclude_keywords=["Java"],
    )

    assert "Java" not in result.added_by_ai
    assert "Java" not in result.expanded_keywords
    assert "Flask" in result.added_by_ai
    assert "FastAPI" in result.added_by_ai


@pytest.mark.asyncio
async def test_parse_enriched_profile_filters_exclude_keywords_case_insensitive(
    monkeypatch,
) -> None:
    fake_model = _FakeModel('{"expanded_keywords": ["JAVA", "Flask"]}')
    _configure_fake_google(monkeypatch, fake_model)

    enricher = ProfileEnricher(settings=_settings())
    result = await enricher.enrich(
        include_keywords=["Python"],
        exclude_keywords=["java"],
    )

    assert "JAVA" not in result.added_by_ai
    assert "JAVA" not in result.expanded_keywords
    assert "Flask" in result.added_by_ai


# ---------------------------------------------------------------------------
# Deduplicação case-insensitive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expanded_keywords_deduplicates_case_insensitively(monkeypatch) -> None:
    # "vue" from AI should not coexist with "Vue" from originals
    fake_model = _FakeModel('{"expanded_keywords": ["vue", "Svelte"]}')
    _configure_fake_google(monkeypatch, fake_model)

    enricher = ProfileEnricher(settings=_settings())
    result = await enricher.enrich(
        include_keywords=["Vue"],
        exclude_keywords=[],
    )

    lower_expanded = [kw.casefold() for kw in result.expanded_keywords]
    assert lower_expanded.count("vue") == 1, "vue deve aparecer apenas uma vez"
    assert "Vue" in result.expanded_keywords  # casing original preservado
    assert "Svelte" in result.expanded_keywords


# ---------------------------------------------------------------------------
# Parse de JSON malformado
# ---------------------------------------------------------------------------


def test_parse_json_response_raises_on_no_json(monkeypatch) -> None:
    fake_model = _FakeModel()
    _configure_fake_google(monkeypatch, fake_model)

    enricher = ProfileEnricher(settings=_settings())
    with pytest.raises(ValueError, match="JSON valido"):
        enricher._parse_json_response("sem json aqui")


def test_parse_json_response_raises_value_error_on_malformed_snippet(monkeypatch) -> None:
    fake_model = _FakeModel()
    _configure_fake_google(monkeypatch, fake_model)

    enricher = ProfileEnricher(settings=_settings())
    with pytest.raises(ValueError, match="malformado"):
        enricher._parse_json_response("prefixo {chave_sem_aspas: valor} sufixo")


def test_parse_json_response_raises_on_non_dict(monkeypatch) -> None:
    fake_model = _FakeModel()
    _configure_fake_google(monkeypatch, fake_model)

    enricher = ProfileEnricher(settings=_settings())
    with pytest.raises(ValueError):
        enricher._parse_json_response('["lista", "nao", "objeto"]')


# ---------------------------------------------------------------------------
# get_effective_search_terms
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_effective_search_terms_returns_originals_on_failure(monkeypatch) -> None:
    async def _failing_build(*_args, **_kwargs):
        raise RuntimeError("Gemini indisponivel")

    monkeypatch.setattr(enricher_module, "build_enriched_profile", _failing_build)

    settings = _settings()
    effective, expanded_set = await get_effective_search_terms(
        search_terms=["Python", "Django"],
        exclude_keywords=[],
        settings=settings,
    )

    assert effective == ["Python", "Django"]
    assert expanded_set is None


@pytest.mark.asyncio
async def test_get_effective_search_terms_returns_originals_without_api_key(
    monkeypatch,
) -> None:
    settings = Settings(
        database_url="sqlite://",
        log_level="INFO",
        request_timeout=10.0,
        remoteok_api_url="https://remoteok.com/api",
        remotar_base_url="https://remotar.com.br",
        remotar_api_url="https://api.remotar.com.br",
        user_agent="test-agent",
        gemini_api_key="",
        gemini_model="models/gemini-2.5-flash-lite",
        gemini_retry_delay_seconds=0.01,
    )

    effective, expanded_set = await get_effective_search_terms(
        search_terms=["Python"],
        exclude_keywords=[],
        settings=settings,
    )

    assert effective == ["Python"]
    assert expanded_set is None


@pytest.mark.asyncio
async def test_get_effective_search_terms_returns_expanded_on_success(monkeypatch) -> None:
    async def _fake_build(include_keywords, exclude_keywords, settings=None):
        return EnrichedProfile(
            original_keywords=tuple(include_keywords),
            expanded_keywords=(*include_keywords, "FastAPI"),
            added_by_ai=("FastAPI",),
        )

    monkeypatch.setattr(enricher_module, "build_enriched_profile", _fake_build)

    effective, expanded_set = await get_effective_search_terms(
        search_terms=["Python"],
        exclude_keywords=[],
        settings=_settings(),
    )

    assert effective == ["Python", "FastAPI"]
    assert expanded_set == {"Python", "FastAPI"}
