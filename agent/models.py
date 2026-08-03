from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Status(str, Enum):
    SUCCESS = "SUCCESS"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNSUPPORTED_REQUEST = "UNSUPPORTED_REQUEST"
    GEMINI_UNAVAILABLE = "GEMINI_UNAVAILABLE"
    EXECUTION_FAILED = "EXECUTION_FAILED"


class AnalysisStep(BaseModel):
    step: int
    description: str


class AnalysisOperation(BaseModel):
    operation: Literal["list_datasets", "inspect_schema", "filter", "select", "sort", "limit", "group_by", "count", "sum", "average", "minimum", "maximum", "distinct", "join", "calculate", "compare", "date_difference", "trend"]
    dataset: str | None = None
    fields: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)


class QuestionUnderstanding(BaseModel):
    intent: str
    question_type: Literal[
        "greeting", "capability", "data_lookup", "data_analysis", "simulation",
        "report_generation", "unsupported", "needs_clarification",
    ]
    normalized_question: str
    requires_factory_data: bool
    required_catalog_topics: list[str] = Field(default_factory=list)
    requested_outputs: list[Literal["cli", "csv", "xlsx", "pdf", "json", "charts"]] = Field(default_factory=lambda: ["cli"])
    confidence: float = Field(ge=0, le=1)


class AnalysisPlan(BaseModel):
    request_id: str
    user_question: str
    intent: str
    catalog_context: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    steps: list[AnalysisStep] = Field(default_factory=list)
    operations: list[AnalysisOperation] = Field(default_factory=list)
    execution_method: Literal["catalog", "operation_executor", "deterministic", "deterministic_query", "sandbox", "sandbox_python", "unsupported", "insufficient_data"]
    requested_outputs: list[Literal["cli", "csv", "xlsx", "pdf", "json", "charts"]] = Field(default_factory=lambda: ["cli"])
    expected_result_columns: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)

    @field_validator("datasets")
    @classmethod
    def known_datasets(cls, value: list[str]) -> list[str]:
        allowed = {"orders", "machines", "inventory"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"unknown datasets: {', '.join(unknown)}")
        return value


class CodeExecutionRequest(BaseModel):
    request_id: str
    code: str
    datasets: list[str]
    requested_outputs: list[str]


class GeneratedFile(BaseModel):
    path: str
    type: Literal["csv", "pdf", "json", "chart"]
    size_bytes: int


class SandboxResult(BaseModel):
    status: Literal["success", "error"]
    summary: dict[str, Any] = Field(default_factory=dict)
    findings: list[dict[str, Any] | str] = Field(default_factory=list)
    evidence: list[dict[str, Any] | str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_files: list[str] = Field(default_factory=list)


class FinalResponse(BaseModel):
    status: Status = Status.SUCCESS
    understanding: str
    plan: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    data_used: list[str] = Field(default_factory=list)
    summary: str
    key_findings: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    confidence: Literal["High", "Medium", "Low"] = "Medium"
    limitations: list[str] = Field(default_factory=list)
    generated_files: list[str] = Field(default_factory=list)
    request_id: str
    reasoning_summary: list[str] = Field(default_factory=list)
    dataset_versions: dict[str, str] = Field(default_factory=dict)

    def to_display_text(self) -> str:
        if self.status != Status.SUCCESS:
            details = self.key_findings or self.limitations
            return "\n\n".join([f"Status: {self.status.value}", self.summary, *details])
        lines = [self.summary]
        if self.key_findings:
            lines.append("\n".join(f"- {item}" for item in self.key_findings))
        if self.evidence:
            lines.append("Details\n" + "\n".join(f"- {item}" for item in self.evidence))
        if self.recommended_actions:
            lines.append("Next steps\n" + "\n".join(f"- {item}" for item in self.recommended_actions))
        if self.limitations:
            lines.append("Limitations\n" + "\n".join(f"- {item}" for item in self.limitations))
        if self.generated_files:
            lines.append("Generated files\n" + "\n".join(f"- {item}" for item in self.generated_files))
        return "\n\n".join(lines)


class AuditRecord(BaseModel):
    request_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    user_question: str
    catalog_entries_used: list[str] = Field(default_factory=list)
    analysis_plan: dict[str, Any] = Field(default_factory=dict)
    generated_code_hash: str | None = None
    code_validation_result: dict[str, Any] = Field(default_factory=dict)
    sandbox_execution_status: str | None = None
    sandbox_execution_time: float | None = None
    datasets_used: list[str] = Field(default_factory=list)
    record_ids_used: list[str] = Field(default_factory=list)
    generated_files: list[str] = Field(default_factory=list)
    evidence_validation: dict[str, Any] = Field(default_factory=dict)
    final_status: str
    model_name: str | None = None
    token_usage: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
