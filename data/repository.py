from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from agent.catalog_context import Catalog
from agent.models import PROJECT_ROOT


class DatasetRepository:
    """Read-only access to the currently approved datasets."""

    DATASETS = ("orders", "machines", "inventory")
    MAX_ROWS = 10_000
    MAX_PREVIEW_ROWS = 50

    def __init__(self, catalog: Catalog | None = None) -> None:
        self.catalog = catalog or Catalog()

    def list_datasets(self) -> dict[str, Any]:
        return {"datasets": [self.get_summary(name) for name in self.DATASETS]}

    def get_schema(self, dataset_name: str) -> dict[str, Any]:
        name = self._validate_name(dataset_name)
        schema = self.catalog.dataset(name)
        path = self._path(name)
        return {
            "dataset": name,
            "description": schema.get("business_purpose", ""),
            "primary_key": schema.get("primary_key"),
            "fields": schema.get("columns", []),
            "active_source": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "dataset_version": self._version(path),
        }

    def get_summary(self, dataset_name: str) -> dict[str, Any]:
        name = self._validate_name(dataset_name)
        path = self._path(name)
        frame = self._read(name)
        schema = self.catalog.dataset(name)
        return {
            "name": name,
            "description": schema.get("business_purpose", ""),
            "row_count": int(len(frame)),
            "fields": [column["name"] for column in schema.get("columns", [])],
            "dataset_version": self._version(path),
        }

    def preview(self, dataset_name: str, limit: int = 5) -> dict[str, Any]:
        name = self._validate_name(dataset_name)
        safe_limit = max(1, min(int(limit), self.MAX_PREVIEW_ROWS))
        frame = self._read(name).head(safe_limit)
        return {"dataset": name, "rows": self._records(frame), "dataset_version": self._version(self._path(name))}

    def read(self, dataset_name: str, columns: Iterable[str] | None = None) -> pd.DataFrame:
        name = self._validate_name(dataset_name)
        frame = self._read(name)
        if columns is not None:
            requested = list(columns)
            allowed = {column["name"] for column in self.catalog.dataset(name).get("columns", [])}
            unknown = sorted(set(requested) - allowed)
            if unknown:
                raise ValueError(f"unknown field(s) for {name}: {', '.join(unknown)}")
            frame = frame[requested]
        return frame.head(self.MAX_ROWS).copy()

    def versions(self, dataset_names: Iterable[str]) -> dict[str, str]:
        return {name: self.get_summary(name)["dataset_version"] for name in dataset_names}

    def _validate_name(self, dataset_name: str) -> str:
        name = str(dataset_name).strip().lower()
        if name not in self.DATASETS:
            raise ValueError(f"unknown dataset: {dataset_name}")
        return name

    def _path(self, dataset_name: str) -> Path:
        location = Path(self.catalog.dataset(dataset_name)["file_location"])
        path = location if location.is_absolute() else PROJECT_ROOT / location
        resolved = path.resolve()
        if not resolved.is_file() or not str(resolved).startswith(str(PROJECT_ROOT.resolve())):
            raise ValueError(f"active dataset is unavailable: {dataset_name}")
        return resolved

    def _read(self, dataset_name: str) -> pd.DataFrame:
        return pd.read_csv(self._path(dataset_name))

    def _version(self, path: Path) -> str:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        return f"{path.stem}_{digest}"

    @staticmethod
    def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
        return json.loads(frame.to_json(orient="records", date_format="iso"))
