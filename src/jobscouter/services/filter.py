from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from sqlmodel import Session

from jobscouter.core.logging import get_logger
from jobscouter.db.models import Job, JobStatus


@dataclass(frozen=True, slots=True)
class FilterRules:
    exclude_keywords: tuple[str, ...] = ()
    include_keywords: tuple[str, ...] = ()


class JobFilterService:
    def __init__(self, session: Session, filters_path: Path | None = None) -> None:
        self.session = session
        self.logger = get_logger("jobscouter.services.filter")
        self.filters_path = filters_path or Path(__file__).resolve().parents[3] / "filters.yaml"
        self.rules = self._load_rules()

    async def classify_job(self, job: Job) -> JobStatus:
        if job.status == JobStatus.analyzed:
            return job.status

        status, reason = self._classify_text(job.title, job.description_raw)
        if job.status != status or job.filter_reason != reason:
            job.status = status
            job.filter_reason = reason
            job.updated_at = datetime.now(timezone.utc)
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

    def _load_rules(self) -> FilterRules:
        yaml_module = self._load_yaml_module()
        if yaml_module is None:
            return FilterRules()

        try:
            with self.filters_path.open("r", encoding="utf-8") as stream:
                payload = yaml_module.safe_load(stream) or {}
        except FileNotFoundError:
            self.logger.warning("Arquivo de filtros nao encontrado em %s. Usando listas vazias.", self.filters_path)
            return FilterRules()
        except Exception as exc:
            self.logger.warning(
                "Falha ao interpretar filters.yaml em %s: %s. Usando listas vazias.",
                self.filters_path,
                exc,
            )
            return FilterRules()

        filters = payload.get("filters") if isinstance(payload, dict) else None
        if not isinstance(filters, dict):
            return FilterRules()

        exclude_keywords = self._normalize_keywords(filters.get("exclude_keywords"))
        include_keywords = self._normalize_keywords(filters.get("include_keywords"))
        return FilterRules(exclude_keywords=exclude_keywords, include_keywords=include_keywords)

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
