from __future__ import annotations

import asyncio
import importlib
import json
import re
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session

from jobscouter.core.config import Settings, get_settings
from jobscouter.core.logging import get_logger
from jobscouter.db.models import Job


PROFILE_TEXT = "Full-stack Developer, Python (Django), Vue.js, PostgreSQL, Linux, Nível Pleno"


@dataclass(frozen=True, slots=True)
class AIAnalysisResult:
    score: int
    summary: str


class AIAnalyzerService:
    NON_DEV_KEYWORDS: tuple[str, ...] = (
        "contador",
        "contabil",
        "contabilidade",
        "vendedor",
        "vendas",
        "designer",
        "design grafico",
        "ux",
        "ui",
        "marketing",
    )

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.logger = get_logger("jobscouter.services.analyzer")

        if not self.settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY nao configurada para analise de IA.")

        self.genai = importlib.import_module("google.generativeai")
        exceptions_module = importlib.import_module("google.api_core.exceptions")
        self.ResourceExhausted = exceptions_module.ResourceExhausted
        self.NotFound = exceptions_module.NotFound

        self.genai.configure(api_key=self.settings.gemini_api_key)
        self._model_candidates = self._build_model_candidates()
        self._model_index = 0
        self.model = self.genai.GenerativeModel(self._model_candidates[self._model_index])

    async def analyze_job(self, job: Job) -> AIAnalysisResult:
        if self._is_non_dev_job(job.title, job.description_raw):
            return AIAnalysisResult(
                score=0,
                summary="Vaga fora de desenvolvimento de software (classificacao local).",
            )

        prompt = self._build_prompt(job)

        try:
            response_text = await self._generate_json_response(prompt)
        except self.ResourceExhausted:
            delay = max(self.settings.gemini_retry_delay_seconds, 0.5)
            self.logger.warning("Rate limit no Gemini para vaga id=%s; retry em %.1fs.", job.id, delay)
            await asyncio.sleep(delay)
            response_text = await self._generate_json_response(prompt)

        payload = self._parse_response(response_text)
        score = self._normalize_score(payload.get("score"))
        summary = self._normalize_summary(payload.get("summary"))

        return AIAnalysisResult(score=score, summary=summary)

    async def _generate_json_response(self, prompt: str) -> str:
        while True:
            try:
                response = await asyncio.to_thread(
                    self.model.generate_content,
                    prompt,
                    generation_config=self.genai.GenerationConfig(response_mime_type="application/json"),
                )
                break
            except self.NotFound:
                if not self._switch_to_fallback_model():
                    raise
        text = getattr(response, "text", "") or ""
        if not text.strip():
            raise ValueError("Resposta vazia do Gemini.")
        return text.strip()

    def _switch_to_fallback_model(self) -> bool:
        next_index = self._model_index + 1
        if next_index >= len(self._model_candidates):
            return False

        self._model_index = next_index
        model_name = self._model_candidates[self._model_index]
        self.logger.warning("Modelo Gemini indisponivel, alternando para: %s", model_name)
        self.model = self.genai.GenerativeModel(model_name)
        return True

    def _build_model_candidates(self) -> tuple[str, ...]:
        candidates: list[str] = [
            self.settings.gemini_model,
            "gemini-1.5-flash",
            "models/gemini-1.5-flash",
            "gemini-1.5-flash-latest",
            "models/gemini-1.5-flash-latest",
        ]

        try:
            for model in self.genai.list_models():
                model_name = getattr(model, "name", "")
                supported_methods = getattr(model, "supported_generation_methods", []) or []
                if model_name and "flash" in model_name.lower() and "generateContent" in supported_methods:
                    candidates.append(model_name)
        except Exception as exc:
            self.logger.warning("Nao foi possivel listar modelos Gemini disponiveis: %s", exc)

        unique_candidates = list(dict.fromkeys(candidates))
        return tuple(unique_candidates)

    def _build_prompt(self, job: Job) -> str:
        description = (job.description_raw or "").strip()
        return (
            "Voce e um classificador objetivo de vagas. "
            "Avalie apenas aderencia tecnica ao perfil alvo. "
            "Se a vaga nao for de desenvolvimento de software, score deve ser 0. "
            "Retorne apenas JSON valido com as chaves score e summary. "
            "Sem markdown. Sem texto fora do JSON.\n\n"
            f"Perfil alvo: {PROFILE_TEXT}\n"
            f"Titulo da vaga: {job.title}\n"
            f"Descricao da vaga: {description}\n\n"
            "Formato obrigatorio: {\"score\": <inteiro 0-10>, \"summary\": \"<texto curto>\"}"
        )

    def _parse_response(self, response_text: str) -> dict[str, Any]:
        try:
            parsed = json.loads(response_text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = response_text.find("{")
        end = response_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Resposta do Gemini nao contem JSON valido.")

        snippet = response_text[start : end + 1]
        parsed = json.loads(snippet)
        if not isinstance(parsed, dict):
            raise ValueError("JSON da analise nao e um objeto.")
        return parsed

    def _normalize_score(self, value: object) -> int:
        if not isinstance(value, (int, float, str)):
            return 0
        try:
            score = int(float(value))
        except (TypeError, ValueError):
            score = 0
        return max(0, min(10, score))

    def _normalize_summary(self, value: object) -> str:
        if isinstance(value, str):
            summary = value.strip()
            if summary:
                return summary[:1000]
        return "Resumo indisponivel."

    def _is_non_dev_job(self, title: str, description: str) -> bool:
        text = f"{title}\n{description}".casefold()
        return any(self._contains_keyword(text, keyword) for keyword in self.NON_DEV_KEYWORDS)

    def _contains_keyword(self, text: str, keyword: str) -> bool:
        # Use word boundaries to avoid substring false positives (e.g. "acquired" -> "ui").
        pattern = rf"\b{re.escape(keyword.casefold())}\b"
        return re.search(pattern, text) is not None
