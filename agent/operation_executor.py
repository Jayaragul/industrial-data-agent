from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from agent.catalog_context import Catalog
from agent.models import AnalysisPlan, PROJECT_ROOT
from data.repository import DatasetRepository


class OperationExecutor:
    def __init__(self, catalog: Catalog | None = None, repository: DatasetRepository | None = None) -> None:
        self.catalog = catalog or Catalog()
        self.repository = repository or DatasetRepository(self.catalog)

    def execute(self, plan: AnalysisPlan) -> dict[str, Any]:
        operation_datasets = {operation.dataset for operation in plan.operations if operation.dataset}
        if len(plan.datasets) > 1 and len(operation_datasets) > 1:
            return self._execute_multi_dataset(plan)
        frames = {dataset: self._read_frame(dataset) for dataset in plan.datasets}
        if not frames:
            return self._error("No dataset was selected for this question.")

        dataset = plan.datasets[0]
        frame = frames[dataset].copy()
        generated_files: list[str] = []
        warnings: list[str] = []

        frame = self._add_known_calculations(dataset, frame)
        frame = self._apply_question_hints(plan, dataset, frame)

        aggregate_result: dict[str, Any] | None = None
        for operation in plan.operations:
            op_dataset = operation.dataset or dataset
            if op_dataset in frames and op_dataset != dataset:
                dataset = op_dataset
                frame = self._add_known_calculations(dataset, frames[dataset].copy())
                frame = self._apply_question_hints(plan, dataset, frame)

            op = operation.operation
            params = operation.parameters or {}
            fields = [field for field in operation.fields if field in frame.columns]

            if op == "filter":
                frame = self._apply_filter(frame, fields, params)
            elif op == "select" and fields:
                frame = frame[fields].copy()
            elif op == "sort":
                frame = self._apply_sort(frame, fields, params, plan.user_question)
            elif op == "limit":
                frame = frame.head(self._int_param(params, ["n", "limit", "count"], 10))
            elif op == "count":
                aggregate_result = {"label": "count", "value": int(len(frame))}
            elif op in {"sum", "average", "minimum", "maximum"}:
                aggregate_result = self._numeric_aggregate(frame, op, fields)
            elif op == "distinct":
                aggregate_result = self._distinct(frame, fields)
            elif op == "group_by":
                aggregate_result = self._group_by(frame, fields, params)
            elif op == "join":
                frame = self._apply_known_join(dataset, frame, frames)
            elif op in {"calculate", "compare", "date_difference", "trend", "inspect_schema"}:
                continue

        frame = self._finish_question_shape(plan, dataset, frame)
        if any(output in plan.requested_outputs for output in ["csv", "xlsx", "json", "charts"]):
            generated_files = self._write_outputs(plan, frame)

        evidence_rows = self._evidence_rows(dataset, frame)
        summary = self._summary(plan, dataset, frame, aggregate_result)
        findings = [{"message": summary}]
        if aggregate_result and aggregate_result.get("rows"):
            evidence_rows = aggregate_result["rows"]

        return {
            "status": "success",
            "summary": {"records_analysed": len(frames[plan.datasets[0]]), "records_returned": len(frame)},
            "findings": findings,
            "evidence": evidence_rows,
            "warnings": warnings,
            "limitations": [],
            "generated_files": generated_files,
        }

    def _execute_multi_dataset(self, plan: AnalysisPlan) -> dict[str, Any]:
        """Execute independent AI-approved operations per dataset and merge evidence."""
        combined_findings: list[dict[str, Any]] = []
        combined_evidence: list[dict[str, Any]] = []
        combined_warnings: list[str] = []
        combined_limitations: list[str] = []
        generated_files: list[str] = []
        records_analysed = 0
        records_returned = 0
        for dataset in plan.datasets:
            operations = [operation for operation in plan.operations if operation.dataset == dataset]
            if not operations:
                continue
            subplan = plan.model_copy(update={
                "datasets": [dataset],
                "operations": operations,
                "requested_outputs": ["cli"],
            })
            result = self.execute(subplan)
            if result.get("status") != "success":
                combined_limitations.extend(result.get("limitations", []))
                continue
            summary = result.get("summary", {})
            records_analysed += int(summary.get("records_analysed", 0))
            records_returned += int(summary.get("records_returned", 0))
            combined_findings.extend({"dataset": dataset, **finding} if isinstance(finding, dict) else {"dataset": dataset, "message": str(finding)} for finding in result.get("findings", []))
            combined_evidence.extend({"dataset": dataset, **row} if isinstance(row, dict) else {"dataset": dataset, "value": row} for row in result.get("evidence", []))
            combined_warnings.extend(result.get("warnings", []))
            combined_limitations.extend(result.get("limitations", []))
        if not combined_findings and not combined_evidence:
            return self._error("The approved multi-dataset operations produced no results.")
        return {
            "status": "success",
            "summary": {"records_analysed": records_analysed, "records_returned": records_returned},
            "findings": combined_findings,
            "evidence": combined_evidence,
            "warnings": combined_warnings,
            "limitations": combined_limitations,
            "generated_files": generated_files,
        }

    def _read_frame(self, dataset: str) -> pd.DataFrame:
        location = Path(self.catalog.dataset(dataset)["file_location"])
        path = location if location.is_absolute() else PROJECT_ROOT / location
        return self.repository.read(dataset)

    def _add_known_calculations(self, dataset: str, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        if dataset == "orders" and {"order_quantity", "completed_quantity"}.issubset(result.columns):
            quantity = pd.to_numeric(result["order_quantity"], errors="coerce").fillna(0)
            completed = pd.to_numeric(result["completed_quantity"], errors="coerce").fillna(0)
            result["remaining_units"] = quantity - completed
            result["progress_percent"] = (completed / quantity.replace(0, pd.NA) * 100).fillna(0).round(1)
        if dataset == "inventory" and {"available_quantity", "reserved_quantity"}.issubset(result.columns):
            available = pd.to_numeric(result["available_quantity"], errors="coerce").fillna(0)
            reserved = pd.to_numeric(result["reserved_quantity"], errors="coerce").fillna(0)
            result["usable_quantity"] = available - reserved
        return result

    def _apply_question_hints(self, plan: AnalysisPlan, dataset: str, frame: pd.DataFrame) -> pd.DataFrame:
        question = plan.user_question.lower()
        result = frame
        if dataset in {"orders", "machines"} and "status" in result.columns:
            status_terms = {
                "delayed": "DELAYED",
                "ready": "READY",
                "active": "ACTIVE",
                "pending": "PENDING",
                "hold": "ON_HOLD",
                "idle": "IDLE",
                "running": "RUNNING",
                "maintenance": "MAINTENANCE",
                "maintanace": "MAINTENANCE",
                "maintainance": "MAINTENANCE",
                "down": "DOWN",
            }
            for word, value in status_terms.items():
                if word in question:
                    result = result[result["status"].astype(str).str.upper().eq(value)]
                    break
        if dataset == "orders" and "priority" in result.columns:
            match = re.search(r"\b(high|medium|low)[\s-]+priority\b", question)
            if match:
                result = result[result["priority"].astype(str).str.upper().eq(match.group(1).upper())]
        if dataset == "inventory" and "reorder" in question and {"available_quantity", "reorder_level"}.issubset(result.columns):
            available = pd.to_numeric(result["available_quantity"], errors="coerce").fillna(0)
            reorder = pd.to_numeric(result["reorder_level"], errors="coerce").fillna(0)
            result = result[available <= reorder]
        return result

    def _apply_filter(self, frame: pd.DataFrame, fields: list[str], params: dict[str, Any]) -> pd.DataFrame:
        result = frame
        conditions = params.get("conditions") if isinstance(params.get("conditions"), list) else [params]
        for condition in conditions:
            if not isinstance(condition, dict):
                continue
            field = condition.get("field") or condition.get("column") or (fields[0] if fields else None)
            if field not in result.columns:
                continue
            value = condition.get("value")
            operator = str(condition.get("operator") or condition.get("op") or "equals").lower()
            series = result[field]
            if value is None:
                continue
            if operator in {"equals", "equal", "=", "==", "eq"}:
                result = result[series.astype(str).str.upper().eq(str(value).upper())]
            elif operator in {"contains", "like"}:
                result = result[series.astype(str).str.contains(str(value), case=False, na=False)]
            elif operator in {">", "gt", "greater_than"}:
                result = result[pd.to_numeric(series, errors="coerce") > float(value)]
            elif operator in {">=", "gte", "at_least"}:
                result = result[pd.to_numeric(series, errors="coerce") >= float(value)]
            elif operator in {"<", "lt", "less_than"}:
                result = result[pd.to_numeric(series, errors="coerce") < float(value)]
            elif operator in {"<=", "lte", "at_most"}:
                result = result[pd.to_numeric(series, errors="coerce") <= float(value)]
        return result

    def _apply_sort(self, frame: pd.DataFrame, fields: list[str], params: dict[str, Any], question: str) -> pd.DataFrame:
        field = params.get("field") or params.get("by") or (fields[0] if fields else None)
        if field not in frame.columns:
            field = self._best_sort_field(frame, question)
        if field not in frame.columns:
            return frame
        direction = str(params.get("direction") or params.get("order") or "").lower()
        ascending = direction in {"asc", "ascending", "lowest", "smallest"} or any(word in question.lower() for word in ["lowest", "least", "smallest"])
        return frame.sort_values(field, ascending=ascending)

    def _finish_question_shape(self, plan: AnalysisPlan, dataset: str, frame: pd.DataFrame) -> pd.DataFrame:
        question = plan.user_question.lower()
        result = frame
        if any(word in question for word in ["highest", "maximum", "max", "top", "most"]):
            field = self._best_sort_field(result, question)
            if field:
                result = result.sort_values(field, ascending=False)
                if not any(operation.operation == "limit" for operation in plan.operations):
                    result = result.head(1)
        if any(word in question for word in ["lowest", "minimum", "min", "least"]):
            field = self._best_sort_field(result, question)
            if field:
                result = result.sort_values(field, ascending=True)
                if not any(operation.operation == "limit" for operation in plan.operations):
                    result = result.head(1)
        if self._is_count_question(question):
            return result
        if len(result) > 20 and "all" not in question:
            return result.head(20)
        return result

    def _best_sort_field(self, frame: pd.DataFrame, question: str) -> str | None:
        candidates = [
            ("capacity", "capacity_per_hour"),
            ("health", "health_score"),
            ("efficiency", "efficiency_percent"),
            ("remaining", "remaining_units"),
            ("quantity", "remaining_units" if "remaining_units" in frame.columns else "order_quantity"),
            ("progress", "progress_percent"),
            ("available", "available_quantity"),
            ("reserved", "reserved_quantity"),
            ("reorder", "reorder_level"),
        ]
        for term, field in candidates:
            if term in question and field in frame.columns:
                return field
        numeric_fields = [column for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])]
        return numeric_fields[0] if numeric_fields else None

    def _numeric_aggregate(self, frame: pd.DataFrame, operation: str, fields: list[str]) -> dict[str, Any] | None:
        field = fields[0] if fields else next((column for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])), None)
        if not field:
            return None
        series = pd.to_numeric(frame[field], errors="coerce")
        value = {
            "sum": series.sum(),
            "average": series.mean(),
            "minimum": series.min(),
            "maximum": series.max(),
        }[operation]
        return {"label": f"{operation} {field}", "value": round(float(value), 2)}

    def _distinct(self, frame: pd.DataFrame, fields: list[str]) -> dict[str, Any] | None:
        field = fields[0] if fields else None
        if not field:
            return None
        rows = [{"field": field, "value": value} for value in sorted(frame[field].dropna().astype(str).unique())]
        return {"label": f"distinct {field}", "value": len(rows), "rows": rows}

    def _group_by(self, frame: pd.DataFrame, fields: list[str], params: dict[str, Any]) -> dict[str, Any] | None:
        field = params.get("field") or params.get("by") or (fields[0] if fields else None)
        if field not in frame.columns:
            return None
        grouped = frame.groupby(field, dropna=False).size().reset_index(name="count")
        rows = grouped.to_dict(orient="records")
        return {"label": f"grouped by {field}", "value": len(rows), "rows": rows}

    def _apply_known_join(self, dataset: str, frame: pd.DataFrame, frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
        result = frame
        if dataset == "orders" and "inventory" in frames and "required_material_id" in result.columns:
            result = result.merge(frames["inventory"], left_on="required_material_id", right_on="material_id", how="left", suffixes=("", "_inventory"))
        return result

    def _write_outputs(self, plan: AnalysisPlan, frame: pd.DataFrame) -> list[str]:
        output_dir = PROJECT_ROOT / "runtime" / "outputs" / plan.request_id
        output_dir.mkdir(parents=True, exist_ok=True)
        generated: list[str] = []
        name = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in plan.intent)
        if "csv" in plan.requested_outputs:
            path = output_dir / f"{name}.csv"
            frame.to_csv(path, index=False)
            generated.append(str(path))
        if "xlsx" in plan.requested_outputs:
            path = output_dir / f"{name}.xlsx"
            frame.to_excel(path, index=False)
            generated.append(str(path))
        if "json" in plan.requested_outputs:
            path = output_dir / f"{name}.json"
            frame.to_json(path, orient="records", indent=2)
            generated.append(str(path))
        if "charts" in plan.requested_outputs:
            path = output_dir / f"{name}_bar.png"
            self._write_chart(frame, path)
            generated.append(str(path))
        return generated

    def _write_chart(self, frame: pd.DataFrame, path: Path) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.figure(figsize=(9, 5))
        if "status" in frame.columns:
            frame["status"].astype(str).value_counts().plot(kind="bar")
        else:
            first = frame.columns[0]
            frame[first].astype(str).value_counts().head(12).plot(kind="bar")
        plt.tight_layout()
        plt.savefig(path)
        plt.close()

    def _evidence_rows(self, dataset: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
        primary_key = self.catalog.dataset(dataset).get("primary_key")
        preferred = {
            "orders": ["order_id", "product", "status", "priority", "remaining_units", "due_date"],
            "machines": ["machine_id", "machine_type", "status", "capacity_per_hour", "efficiency_percent", "health_score", "next_available_at"],
            "inventory": ["material_id", "material_name", "available_quantity", "reserved_quantity", "reorder_level", "usable_quantity", "unit"],
        }.get(dataset, [])
        fields = [field for field in preferred if field in frame.columns]
        if primary_key in frame.columns and primary_key not in fields:
            fields.insert(0, primary_key)
        if not fields:
            fields = list(frame.columns[:8])
        return frame[fields].fillna("").to_dict(orient="records")

    def _summary(self, plan: AnalysisPlan, dataset: str, frame: pd.DataFrame, aggregate: dict[str, Any] | None) -> str:
        question = plan.user_question.lower()
        if aggregate:
            return f"{aggregate['label']}: {aggregate['value']}."
        if dataset == "machines" and ("maintenance" in question or "maintanace" in question):
            return self._count_message(len(frame), "machine in maintenance", "machines in maintenance")
        if self._is_count_question(question):
            return self._count_message(len(frame), f"{dataset[:-1]} record" if dataset.endswith("s") else f"{dataset} record")
        return self._count_message(len(frame), f"matching {dataset[:-1]} record" if dataset.endswith("s") else f"matching {dataset} record")

    def _is_count_question(self, question: str) -> bool:
        return any(phrase in question for phrase in ["how many", "number", "count", "no of"])

    def _count_message(self, count: int, singular: str, plural: str | None = None) -> str:
        noun = singular if count == 1 else plural or f"{singular}s"
        return f"{count} {noun} found."

    def _int_param(self, params: dict[str, Any], names: list[str], default: int) -> int:
        for name in names:
            try:
                return int(params[name])
            except (KeyError, TypeError, ValueError):
                continue
        return default

    def _error(self, message: str) -> dict[str, Any]:
        return {"status": "error", "findings": [], "evidence": [], "limitations": [message], "warnings": [], "generated_files": []}
