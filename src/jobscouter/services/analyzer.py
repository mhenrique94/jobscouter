from __future__ import annotations

import asyncio
import importlib
import json
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlmodel import Session

from jobscouter.core.config import Settings, get_settings
from jobscouter.core.logging import get_logger
from jobscouter.db.models import Job
from jobscouter.services.filter import JobFilterService

PROFILE_TEXT = "Full-stack Developer, Python (Django), Vue.js, PostgreSQL, Linux, Nível Pleno"
CANDIDATE_LOCATION_TEXT = "Brasil"


@dataclass(frozen=True, slots=True)
class AIAnalysisResult:
    score: int
    summary: str


class AIAnalyzerService:
    LOW_COST_MODEL_FAMILIES: tuple[str, ...] = (
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
    )
    DEFAULT_LOW_COST_MODELS: tuple[str, ...] = (
        "models/gemini-2.5-flash-lite",
        "gemini-2.5-flash-lite",
        "models/gemini-2.5-flash",
        "gemini-2.5-flash",
    )
    NON_DEV_KEYWORDS: tuple[str, ...] = (
        "contador",
        "contabil",
        "contabilidade",
        "data science",
        "cientista de dados",
        "data scientist",
        "data engineering",
        "engenheiro de dados",
        "data engineer",
        "analytics engineer",
        "business intelligence",
        "bi analyst",
        "analista bi",
        "vendedor",
        "vendas",
        "sales",
        "sdr",
        "bdr",
        "account executive",
        "designer",
        "design grafico",
        "marketing",
        "growth",
    )

    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        filters_path: Path | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.logger = get_logger("jobscouter.services.analyzer")
        self.filter_rules = JobFilterService(session, filters_path=filters_path).rules

        if not self.settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY nao configurada para analise de IA.")

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r"(?s).*google\.generativeai.*",
                category=FutureWarning,
            )
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
            switched = self._switch_to_fallback_model()
            if switched:
                self.logger.warning(
                    "Rate limit no Gemini para vaga id=%s; alternando para modelo fallback.",
                    job.id,
                )
            delay = max(self.settings.gemini_retry_delay_seconds, 0.5)
            self.logger.warning(
                "Rate limit no Gemini para vaga id=%s; retry em %.1fs.", job.id, delay
            )
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
                    generation_config=self.genai.GenerationConfig(
                        response_mime_type="application/json"
                    ),
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
        candidates: list[str] = []

        preferred_model = self.settings.gemini_model.strip()
        if preferred_model and self._is_low_cost_model(preferred_model):
            candidates.append(preferred_model)
        elif preferred_model:
            self.logger.warning(
                "Modelo preferencial fora da allowlist de baixo custo (%s). Ignorando para reduzir risco de faturamento.",
                preferred_model,
            )

        candidates.extend(self.DEFAULT_LOW_COST_MODELS)

        try:
            for model in self.genai.list_models():
                model_name = getattr(model, "name", "")
                supported_methods = getattr(model, "supported_generation_methods", []) or []
                if (
                    model_name
                    and self._is_low_cost_model(model_name)
                    and "generateContent" in supported_methods
                ):
                    candidates.append(model_name)
        except Exception as exc:
            self.logger.warning("Nao foi possivel listar modelos Gemini disponiveis: %s", exc)

        unique_candidates = list(dict.fromkeys(candidates))
        return tuple(unique_candidates)

    def _is_low_cost_model(self, model_name: str) -> bool:
        normalized = model_name.strip().lower()
        if normalized.startswith("models/"):
            normalized = normalized[len("models/") :]
        return normalized in self.LOW_COST_MODEL_FAMILIES

    def _build_prompt(self, job: Job) -> str:
        description = (job.description_raw or "").strip()
        include_keywords = self._format_keywords(self.filter_rules.include_keywords)
        exclude_keywords = self._format_keywords(self.filter_rules.exclude_keywords)
        return (
            "Voce e um Tech Sourcer. Avalie a vaga abaixo comparando-a com as preferencias do candidato. Responda SEMPRE em portugues do Brasil.\n\n"
            f"TECNOLOGIAS DESEJADAS (CORE STACK): {include_keywords}\n"
            f"TECNOLOGIAS/TERMOS A EVITAR: {exclude_keywords}\n"
            f"PERFIL ALVO COMPLEMENTAR: {PROFILE_TEXT}\n\n"
            f"LOCALIZACAO DO CANDIDATO: {CANDIDATE_LOCATION_TEXT}\n\n"
            "INSTRUCOES:\n"
            "REGRAS DE VETO DE LOCALIZACAO (prioridade maxima):\n"
            "- Identifique a localidade exigida pela vaga.\n"
            "- Se a vaga for remota e restrita ao Brasil/Brazil, ela e elegivel (nao aplicar veto de localizacao).\n"
            "- Se a vaga for remota e restrita a LATAM/America Latina, ela e elegivel.\n"
            "- Se a vaga for Remote Global/Worldwide/Anywhere, ela e elegivel independentemente do pais da empresa.\n"
            "- Se a vaga exigir residencia ou autorizacao de trabalho em pais especifico diferente do Brasil e NAO mencionar Remote Global, aceita candidatos de qualquer lugar, visto ou relocacao, o score deve ser 0.\n"
            "- Nesses casos, o summary deve comecar obrigatoriamente com o prefixo [VETO - Localizacao].\n"
            "REGRAS DE VETO DE FUNCAO:\n"
            "- Se a vaga for de area correlata mas nao identica (Data Science, Data Engineering puro, BI, Analytics, Marketing, Sales e correlatas), o score deve ser 0.\n"
            "- O foco exclusivo e Software Development / Engineering.\n"
            "REGRAS DE PONTUACAO (MATCH):\n"
            "Siga este processo em ordem:\n"
            f"PASSO 1 - Liste quais include_keywords ({include_keywords}) aparecem LITERALMENTE no texto da vaga (titulo + descricao).\n"
            f"PASSO 2 - Para include_keywords NAO encontradas no texto, avalie se voce tem conhecimento externo confiavel de que a empresa ou produto usa essa tecnologia (ex: saber que determinada empresa usa Django). Liste separadamente como 'inferido (conhecimento externo)'.\n"
            "PASSO 3 - Some: keywords explicitas valem 1 ponto cada; keywords inferidas valem 0.5 ponto cada.\n"
            "PASSO 4 - Determine o score com base na soma:\n"
            "  * 3 ou mais pontos: score entre 8 e 10.\n"
            "  * 1.5 a 2.5 pontos: score entre 6 e 7.\n"
            "  * 0.5 a 1 ponto: score entre 4 e 5.\n"
            "  * 0 pontos, papel e Software Engineering: score 4.\n"
            "  * 0 pontos, papel ambiguo: score entre 1 e 3.\n"
            "PASSO 5 - Se encontrou exclude_keywords no texto da vaga, reduza o score em 1-2 pontos por termo.\n"
            "PASSO 6 - Monte o summary com: (a) keywords encontradas no texto; (b) tecnologias inferidas por conhecimento externo, marcadas explicitamente como '[inferido]'; (c) justificativa do score.\n"
            "- Retorne apenas JSON valido com as chaves score e summary.\n"
            "- Sem markdown. Sem texto fora do JSON.\n\n"
            f"Titulo da vaga: {job.title}\n"
            f"Descricao da vaga: {description}\n\n"
            'Formato obrigatorio: {"score": <inteiro 0-10>, "summary": "<texto curto>"}'
        )

    def _format_keywords(self, keywords: tuple[str, ...]) -> str:
        if not keywords:
            return "Nenhuma informada"
        return ", ".join(keywords)

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
