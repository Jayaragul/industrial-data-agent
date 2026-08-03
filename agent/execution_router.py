from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.models import AnalysisPlan
from data.repository import DatasetRepository


class ExecutionRouter:
    """Dispatch only after a validated plan chooses the execution method."""

    def __init__(self, repository: DatasetRepository, operation_executor: Any, deterministic_executor: Callable[[AnalysisPlan], dict[str, Any]]) -> None:
        self.repository = repository
        self.operation_executor = operation_executor
        self.deterministic_executor = deterministic_executor

    def execute(self, plan: AnalysisPlan) -> dict[str, Any]:
        if plan.execution_method == "catalog":
            return self._catalog(plan)
        if plan.execution_method == "operation_executor":
            return self.operation_executor.execute(plan)
        if plan.execution_method in {"deterministic", "deterministic_query"}:
            return self.deterministic_executor(plan)
        return {"status": "unsupported_execution_method", "error": f"Unsupported execution method: {plan.execution_method}"}

    def _catalog(self, plan: AnalysisPlan) -> dict[str, Any]:
        if any(operation.operation == "list_datasets" for operation in plan.operations):
            datasets = self.repository.list_datasets()["datasets"]
            evidence = [f"{item['name']}: {item['row_count']} records; fields: {', '.join(item['fields'])}" for item in datasets]
            return {"status": "success", "summary": {"records_returned": len(datasets)}, "findings": [{"message": f"{len(datasets)} datasets are available."}], "evidence": evidence, "warnings": [], "limitations": [], "generated_files": []}
        return {"status": "insufficient_data", "limitations": ["The catalog plan did not request a supported catalog operation."]}
