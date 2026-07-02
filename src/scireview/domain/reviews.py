from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SynthesisClaim(BaseModel):
    """A synthesized claim traceable to extracted evidence."""

    model_config = ConfigDict(extra="forbid")

    claim: str
    evidence_ids: list[str] = Field(min_length=1)


class ReviewSummary(BaseModel):
    """Minimal review synthesis output."""

    model_config = ConfigDict(extra="forbid")

    comparison_summary: list[SynthesisClaim] = Field(default_factory=list)
    agreements: list[SynthesisClaim] = Field(default_factory=list)
    disagreements: list[SynthesisClaim] = Field(default_factory=list)
    methodological_differences: list[SynthesisClaim] = Field(default_factory=list)
    commonly_reported_limitations: list[SynthesisClaim] = Field(default_factory=list)
