from __future__ import annotations

import asyncio
import importlib
import json
import warnings
from dataclasses import dataclass
from typing import Any

from jobscouter.core.config import Settings, get_settings
from jobscouter.core.logging import get_logger


@dataclass(frozen=True, slots=True)
class EnrichedProfile:
    original_keywords: tuple[str, ...]
    expanded_keywords: tuple[str, ...]  # original + AI-added, deduplicated
    added_by_ai: tuple[str, ...]  # net-new terms only (for logging + prompt)


class ProfileEnricher:
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

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.logger = get_logger("jobscouter.services.profile_enricher")

        if not self.settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY nao configurada para expansao de perfil.")

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

    async def enrich(
        self,
        include_keywords: list[str],
        exclude_keywords: list[str],
    ) -> EnrichedProfile:
        if not include_keywords:
            return EnrichedProfile(original_keywords=(), expanded_keywords=(), added_by_ai=())

        prompt = self._build_prompt(include_keywords, exclude_keywords)

        try:
            response_text = await self._generate_json_response(prompt)
        except self.ResourceExhausted:
            switched = self._switch_to_fallback_model()
            if switched:
                self.logger.warning(
                    "Rate limit no Gemini para expansao de perfil; alternando modelo."
                )
            delay = max(self.settings.gemini_retry_delay_seconds, 0.5)
            await asyncio.sleep(delay)
            response_text = await self._generate_json_response(prompt)

        return self._parse_enriched_profile(response_text, include_keywords)

    def _build_prompt(
        self,
        include_keywords: list[str],
        exclude_keywords: list[str],
    ) -> str:
        include_str = ", ".join(include_keywords)
        exclude_str = ", ".join(exclude_keywords) if exclude_keywords else "Nenhuma"
        return (
            "Voce e um especialista em tecnologia. "
            "Para cada termo de inclusao, expanda o conjunto de busca conforme as regras abaixo.\n\n"
            f"TERMOS DE INCLUSAO: {include_str}\n"
            f"TERMOS A EXCLUIR (nao inclua estes nem seus sinonimos): {exclude_str}\n\n"
            "INSTRUCOES:\n"
            "- Se o termo for um FRAMEWORK ou BIBLIOTECA: adicione ate 3 frameworks alternativos "
            "do mesmo tipo e proposito (ex: Django -> Flask, FastAPI; React -> Vue, Svelte).\n"
            "- Se o termo for uma LINGUAGEM DE PROGRAMACAO: adicione os principais frameworks "
            "e bibliotecas usados com ela (ex: Python -> Django, Flask, FastAPI; "
            "JavaScript -> React, Vue, Node.js).\n"
            "- Se o termo for um conceito generico (ex: fullstack, backend, frontend), "
            "NAO adicione nada para ele.\n"
            "- Maximo de 3 sugestoes por termo de entrada.\n"
            "- Nao repita termos ja presentes nos termos de inclusao.\n"
            "- Nunca inclua qualquer termo da lista de exclusao.\n"
            "- Nao inclua: bancos de dados, ORMs, filas, cache, "
            "containers, cloud services ou ferramentas de build/infra.\n"
            "- Retorne apenas JSON valido com a chave expanded_keywords contendo uma lista de strings.\n"
            "- Sem markdown. Sem texto fora do JSON.\n\n"
            'Formato obrigatorio: {"expanded_keywords": ["termo1", "termo2", ...]}'
        )

    def _parse_enriched_profile(
        self,
        response_text: str,
        original_keywords: list[str],
    ) -> EnrichedProfile:
        payload = self._parse_json_response(response_text)
        raw = payload.get("expanded_keywords", [])
        if not isinstance(raw, list):
            raw = []

        ai_suggestions = [item.strip() for item in raw if isinstance(item, str) and item.strip()]

        original_lower = {kw.casefold() for kw in original_keywords}
        added_by_ai = [kw for kw in ai_suggestions if kw.casefold() not in original_lower]

        expanded_keywords = list(dict.fromkeys([*original_keywords, *added_by_ai]))

        if added_by_ai:
            self.logger.info(
                "Perfil expandido: %s -> [%s]",
                ", ".join(original_keywords),
                ", ".join(expanded_keywords),
            )
        else:
            self.logger.info("Expansao de perfil: nenhum termo novo adicionado pela IA.")

        return EnrichedProfile(
            original_keywords=tuple(original_keywords),
            expanded_keywords=tuple(expanded_keywords),
            added_by_ai=tuple(added_by_ai),
        )

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
            raise ValueError("Resposta vazia do Gemini na expansao de perfil.")
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
                "Modelo preferencial fora da allowlist de baixo custo (%s). Ignorando.",
                preferred_model,
            )

        candidates.extend(self.DEFAULT_LOW_COST_MODELS)

        unique_candidates = list(dict.fromkeys(candidates))
        return tuple(unique_candidates)

    def _is_low_cost_model(self, model_name: str) -> bool:
        normalized = model_name.strip().lower()
        if normalized.startswith("models/"):
            normalized = normalized[len("models/") :]
        return normalized in self.LOW_COST_MODEL_FAMILIES

    def _parse_json_response(self, response_text: str) -> dict[str, Any]:
        try:
            parsed = json.loads(response_text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = response_text.find("{")
        end = response_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Resposta do Gemini nao contem JSON valido na expansao de perfil.")

        snippet = response_text[start : end + 1]
        parsed = json.loads(snippet)
        if not isinstance(parsed, dict):
            raise ValueError("JSON retornado pelo Gemini nao e um objeto.")
        return parsed


async def build_enriched_profile(
    include_keywords: list[str],
    exclude_keywords: list[str],
    settings: Settings | None = None,
) -> EnrichedProfile:
    enricher = ProfileEnricher(settings=settings)
    return await enricher.enrich(include_keywords, exclude_keywords)
