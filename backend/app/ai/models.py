"""AI analysis domain models (P3)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Evidence(BaseModel):
    quote: str = Field(min_length=6)
    source_url: str = Field(min_length=1)
    published_at: str | None = None


class AnalysisResult(BaseModel):
    event_type: str = Field(min_length=1)
    sentiment: Literal["positive", "negative", "neutral"]
    materiality: Literal["L1", "L2", "L3", "L4"]
    summary: str = Field(min_length=1, max_length=500)
    stocks: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(min_length=1)

    @model_validator(mode="after")
    def _evidence_required(self) -> "AnalysisResult":
        if not any(e.quote.strip() for e in self.evidence):
            raise ValueError("evidence quote must not be empty")
        return self

