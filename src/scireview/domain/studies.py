from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scireview.domain.evidence import EvidenceSpan


class MethodItem(BaseModel):
    """A method used in the current paper."""

    model_config = ConfigDict(extra="forbid")

    category: str
    description: str
    parameters: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class QuantitativeResult(BaseModel):
    """A reported quantitative result with both raw and parsed values."""

    model_config = ConfigDict(extra="forbid")

    outcome: str
    raw_value: str
    numeric_value: float | None = None
    unit: str | None = None
    uncertainty: str | None = None
    statistical_test: str | None = None
    conditions: str | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class StudyRecord(BaseModel):
    """Validated extraction output for one paper."""

    model_config = ConfigDict(extra="forbid")

    paper_id: str
    research_question: str | None = None
    study_design: str | None = None
    studied_system: str | None = None
    sample_or_dataset_size: str | None = None
    comparator: str | None = None
    methods: list[MethodItem] = Field(default_factory=list)
    results: list[QuantitativeResult] = Field(default_factory=list)
    main_conclusions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def warn_for_missing_evidence(self) -> StudyRecord:
        warnings = list(self.extraction_warnings)
        for index, method in enumerate(self.methods):
            if not method.evidence:
                warnings.append(f"method[{index}] has no supporting evidence")
        for index, result in enumerate(self.results):
            if not result.evidence:
                warnings.append(f"result[{index}] has no supporting evidence")
        self.extraction_warnings = warnings
        return self
