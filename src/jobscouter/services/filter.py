from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path

from sqlmodel import Session, select

from jobscouter.core.logging import get_logger
from jobscouter.db.models import FilterConfig, Job, JobStatus, utcnow


def validate_job_assertiveness(
    job_content: str,
    keywords: set[str],
    threshold: int = 3,
) -> tuple[bool, int]:
    """Retorna (é_assertivo, contagem_de_matches).

    Retorna (True, 0) quando keywords está vazio (validação desabilitada).
    Usa limites de palavra (\\b) para evitar falsos positivos por substring
    (ex.: keyword "go" não casa com "django").
    """
    if not keywords:
        return True, 0
    content_lower = job_content.casefold()
    match_count = sum(
        1 for kw in keywords if re.search(r"\b" + re.escape(kw.casefold()) + r"\b", content_lower)
    )
    return match_count >= threshold, match_count


@dataclass(frozen=True, slots=True)
class FilterRules:
    exclude_keywords: tuple[str, ...] = ()
    include_keywords: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FilterConfigData:
    search_terms: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    include_keywords: tuple[str, ...] = ()

    def to_rules(self) -> FilterRules:
        return FilterRules(
            exclude_keywords=self.exclude_keywords,
            include_keywords=self.include_keywords,
        )


class FilterConfigService:
    def __init__(self, session: Session, filters_path: Path | None = None) -> None:
        self.session = session
        self.logger = get_logger("jobscouter.services.filter")
        self.filters_path = filters_path or Path(__file__).resolve().parents[3] / "filters.yaml"

    def get_active_config(self) -> FilterConfigData:
        model = self.get_active_model()
        if model is not None:
            return self._to_data(model)
        return self._load_yaml_config()

    def get_active_model(self) -> FilterConfig | None:
        model = self.session.exec(select(FilterConfig).where(FilterConfig.id == 1)).first()
        if model is not None:
            return model
        return self.session.exec(select(FilterConfig)).first()

    def seed_if_empty(self) -> FilterConfig:
        existing = self.get_active_model()
        if existing is not None:
            return existing

        payload = self._load_yaml_config()
        created = FilterConfig(
            id=1,
            search_terms=list(payload.search_terms),
            include_keywords=list(payload.include_keywords),
            exclude_keywords=list(payload.exclude_keywords),
            updated_at=utcnow(),
        )
        self.session.add(created)
        self.session.flush()
        return created

    def update_active(
        self,
        *,
        search_terms: list[str] | None = None,
        include_keywords: list[str] | None = None,
        exclude_keywords: list[str] | None = None,
    ) -> FilterConfig:
        model = self.get_active_model()
        if model is None:
            model = self.seed_if_empty()

        changed = False
        if search_terms is not None:
            model.search_terms = list(self._normalize_keywords(search_terms))
            changed = True
        if include_keywords is not None:
            model.include_keywords = list(self._normalize_keywords(include_keywords))
            changed = True
        if exclude_keywords is not None:
            model.exclude_keywords = list(self._normalize_keywords(exclude_keywords))
            changed = True

        if changed:
            model.updated_at = utcnow()
            self.session.add(model)
            self.session.flush()

        return model

    def _to_data(self, model: FilterConfig) -> FilterConfigData:
        return FilterConfigData(
            search_terms=self._normalize_keywords(model.search_terms),
            exclude_keywords=self._normalize_keywords(model.exclude_keywords),
            include_keywords=self._normalize_keywords(model.include_keywords),
        )

    def _load_yaml_config(self) -> FilterConfigData:
        yaml_module = self._load_yaml_module()
        if yaml_module is None:
            return FilterConfigData()

        try:
            with self.filters_path.open("r", encoding="utf-8") as stream:
                payload = yaml_module.safe_load(stream) or {}
        except FileNotFoundError:
            self.logger.warning(
                "Arquivo de filtros nao encontrado em %s. Usando listas vazias.", self.filters_path
            )
            return FilterConfigData()
        except Exception as exc:
            self.logger.warning(
                "Falha ao interpretar filters.yaml em %s: %s. Usando listas vazias.",
                self.filters_path,
                exc,
            )
            return FilterConfigData()

        if not isinstance(payload, dict):
            return FilterConfigData()

        raw_search_terms = payload.get("search_terms")
        filters = payload.get("filters") if isinstance(payload, dict) else None
        if not isinstance(filters, dict):
            filters = {}

        return FilterConfigData(
            search_terms=self._normalize_keywords(raw_search_terms),
            exclude_keywords=self._normalize_keywords(filters.get("exclude_keywords")),
            include_keywords=self._normalize_keywords(filters.get("include_keywords")),
        )

    def _normalize_keywords(self, value: object) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())

    def _load_yaml_module(self):
        try:
            return import_module("yaml")
        except ModuleNotFoundError:
            self.logger.warning("Dependencia PyYAML indisponivel. Usando listas vazias de filtros.")
            return None


class JobFilterService:
    def __init__(self, session: Session, filters_path: Path | None = None) -> None:
        self.session = session
        self.logger = get_logger("jobscouter.services.filter")
        self.filters_path = filters_path or Path(__file__).resolve().parents[3] / "filters.yaml"
        self.config_service = FilterConfigService(session, filters_path=self.filters_path)
        self.rules = self.config_service.get_active_config().to_rules()

    async def classify_job(self, job: Job) -> JobStatus:
        if job.status == JobStatus.analyzed:
            return job.status

        status, reason = self._classify_text(job.title, job.description_raw)
        if job.status != status or job.filter_reason != reason:
            job.status = status
            job.filter_reason = reason
            job.updated_at = datetime.now(UTC)
            self.session.add(job)
            self.session.flush()

        return job.status

    def _classify_text(self, title: str, description_raw: str) -> tuple[JobStatus, str | None]:
        combined_text = f"{title}\n{description_raw}".casefold()

        excluded_keyword = self._first_match(combined_text, self.rules.exclude_keywords)
        if excluded_keyword is not None:
            return JobStatus.discarded, f"Palavra excluida: {excluded_keyword}"

        included_keyword = self._first_match(combined_text, self.rules.include_keywords)
        if included_keyword is not None:
            return JobStatus.ready_for_ai, None

        return JobStatus.pending, None

    def _first_match(self, text: str, keywords: tuple[str, ...]) -> str | None:
        for keyword in keywords:
            if keyword.casefold() in text:
                return keyword
        return None
