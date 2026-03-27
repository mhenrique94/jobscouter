from __future__ import annotations

from pydantic import BaseModel, Field


class FilterConfigResponse(BaseModel):
    search_terms: list[str]
    include_keywords: list[str]
    exclude_keywords: list[str]


class FilterConfigPatchRequest(BaseModel):
    search_terms: list[str] | None = Field(default=None)
    include_keywords: list[str] | None = Field(default=None)
    exclude_keywords: list[str] | None = Field(default=None)
