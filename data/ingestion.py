from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd

from agent.catalog_context import Catalog
from agent.models import PROJECT_ROOT
from data.normalizers import normalize_status
from data.validators import require_columns
from knowledge.wiki import FactoryWiki


class DataIngestionService:
    """Validates user files and activates them as the current agent datasets."""

    DATASETS = {"orders", "machines", "inventory"}
    REGISTRY_PATH = PROJECT_ROOT / "runtime" / "ingested" / "active_sources.json"

    def __init__(self, catalog: Catalog | None = None, storage_dir: Path | None = None) -> None:
        self.catalog = catalog or Catalog()
        self.registry_path = (storage_dir or self.REGISTRY_PATH.parent) / "active_sources.json"
        self.wiki = FactoryWiki() if storage_dir is None else None

    def ingest(self, dataset: str, source: str | Path) -> dict[str, Any]:
        dataset = dataset.strip().lower()
        if dataset not in self.DATASETS:
            raise ValueError("dataset must be one of: orders, machines, inventory")
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise ValueError(f"file not found: {source_path}")
        if source_path.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
            raise ValueError("only CSV and Excel (.xlsx or .xls) files are supported")

        try:
            frame = pd.read_csv(source_path) if source_path.suffix.lower() == ".csv" else pd.read_excel(source_path)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise ValueError(f"could not read {source_path.name}: {exc}") from exc
        frame.columns = [str(column).strip() for column in frame.columns]
        schema = self.catalog.dataset(dataset)
        required = {column["name"] for column in schema.get("columns", [])}
        require_columns(set(frame.columns), required)
        frame = frame.loc[:, [column["name"] for column in schema["columns"]]].copy()
        if frame.empty:
            raise ValueError("the file has no data rows")
        if frame[schema["primary_key"]].isna().any() or (frame[schema["primary_key"]].astype(str).str.strip() == "").any():
            raise ValueError(f"{schema['primary_key']} cannot be blank")
        if frame[schema["primary_key"]].astype(str).duplicated().any():
            raise ValueError(f"{schema['primary_key']} values must be unique")

        for column in schema.get("columns", []):
            name = column["name"]
            if column.get("type") == "enum":
                frame[name] = frame[name].map(normalize_status)
                allowed = set(column.get("allowed_values", []))
                invalid = sorted(set(frame.loc[~frame[name].isin(allowed), name]))
                if invalid:
                    raise ValueError(f"invalid {name} value(s): {', '.join(invalid)}")
            elif column.get("type") == "number":
                frame[name] = pd.to_numeric(frame[name], errors="coerce")
                if frame[name].isna().any():
                    raise ValueError(f"{name} must contain numbers")

        destination_dir = self.registry_path.parent
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{dataset}.csv"
        frame.to_csv(destination, index=False, quoting=csv.QUOTE_MINIMAL)
        registry = self.active_sources()
        try:
            stored_path = str(destination.relative_to(PROJECT_ROOT)).replace("\\", "/")
        except ValueError:
            stored_path = str(destination)
        registry[dataset] = stored_path
        self.registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        wiki_page = self.wiki.ingest(dataset, source_path, destination) if self.wiki else None
        return {"dataset": dataset, "records": len(frame), "path": str(destination), "source": str(source_path), "wiki_page": str(wiki_page) if wiki_page else None}

    def active_sources(self) -> dict[str, str]:
        if not self.registry_path.is_file():
            return {}
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
            return {name: path for name, path in data.items() if name in self.DATASETS and isinstance(path, str)}
        except (OSError, json.JSONDecodeError):
            return {}
