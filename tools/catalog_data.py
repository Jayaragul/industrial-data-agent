from __future__ import annotations

from data.repository import DatasetRepository
import pandas as pd


def list_datasets(repository: DatasetRepository) -> dict[str, object]:
    return repository.list_datasets()


def describe_dataset(repository: DatasetRepository, dataset: str) -> dict[str, object]:
    return repository.get_schema(dataset)


def preview_dataset(repository: DatasetRepository, dataset: str, limit: int = 5) -> dict[str, object]:
    return repository.preview(dataset, limit)


def get_distinct_values(repository: DatasetRepository, dataset: str, field: str, limit: int = 50) -> dict[str, object]:
    frame = repository.read(dataset, [field])
    values = frame[field].dropna().astype(str).drop_duplicates().head(max(1, min(limit, 50))).tolist()
    return {"dataset": dataset, "field": field, "values": values, "dataset_version": repository.get_summary(dataset)["dataset_version"]}


def get_column_statistics(repository: DatasetRepository, dataset: str, fields: list[str]) -> dict[str, object]:
    frame = repository.read(dataset, fields)
    statistics: dict[str, object] = {}
    for field in fields:
        numeric = frame[field].apply(lambda value: float(value) if str(value).replace(".", "", 1).isdigit() else None).dropna()
        statistics[field] = {"count": int(frame[field].notna().sum()), "minimum": numeric.min() if not numeric.empty else None, "maximum": numeric.max() if not numeric.empty else None}
    return {"dataset": dataset, "statistics": statistics, "dataset_version": repository.get_summary(dataset)["dataset_version"]}


def query_dataset(repository: DatasetRepository, dataset: str, filters: list[dict[str, object]] | None = None, columns: list[str] | None = None, limit: int = 100) -> dict[str, object]:
    frame = repository.read(dataset, columns)
    for condition in filters or []:
        field = condition.get("field")
        if field not in frame.columns:
            raise ValueError(f"unknown filter field: {field}")
        operator = str(condition.get("operator", "equals")).lower()
        value = condition.get("value")
        if operator in {"equals", "=", "=="}:
            frame = frame[frame[field].astype(str).str.upper() == str(value).upper()]
        elif operator in {"contains", "like"}:
            frame = frame[frame[field].astype(str).str.contains(str(value), case=False, na=False)]
        elif operator in {">", ">=", "<", "<="}:
            numeric = pd.to_numeric(frame[field], errors="coerce")
            threshold = float(value)
            frame = frame[{">": numeric > threshold, ">=": numeric >= threshold, "<": numeric < threshold, "<=": numeric <= threshold}[operator]]
        else:
            raise ValueError(f"unsupported filter operator: {operator}")
    safe_limit = max(1, min(int(limit), repository.MAX_PREVIEW_ROWS * 20))
    return {"dataset": dataset, "rows": repository._records(frame.head(safe_limit)), "matched_rows": int(len(frame)), "dataset_version": repository.get_summary(dataset)["dataset_version"]}


def aggregate_dataset(repository: DatasetRepository, dataset: str, field: str, operation: str, filters: list[dict[str, object]] | None = None) -> dict[str, object]:
    result = query_dataset(repository, dataset, filters, [field], repository.MAX_ROWS)
    values = pd.to_numeric(pd.DataFrame(result["rows"])[field], errors="coerce")
    operation = operation.lower()
    functions = {"count": len, "sum": values.sum, "average": values.mean, "minimum": values.min, "maximum": values.max}
    if operation not in functions:
        raise ValueError(f"unsupported aggregate operation: {operation}")
    value = functions[operation]()
    return {"dataset": dataset, "field": field, "operation": operation, "value": int(value) if operation == "count" else float(value), "dataset_version": result["dataset_version"]}
