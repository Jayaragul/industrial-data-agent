from __future__ import annotations

from pathlib import Path
from typing import Any
import re

import yaml

from agent.models import PROJECT_ROOT
from knowledge.wiki import FactoryWiki


class Catalog:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or PROJECT_ROOT / "llm_wiki"

    def load_yaml(self, relative_path: str) -> Any:
        path = (self.root / relative_path).resolve()
        if not str(path).startswith(str(self.root.resolve())):
            raise ValueError("catalog path escapes llm_wiki")
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def index(self) -> dict[str, Any]:
        return self.load_yaml("index.yaml")

    def dataset(self, name: str) -> dict[str, Any]:
        if name not in {"orders", "machines", "inventory"}:
            raise ValueError(f"unknown dataset: {name}")
        data = self.load_yaml(f"datasets/{name}.yaml")
        registry_path = PROJECT_ROOT / "runtime" / "ingested" / "active_sources.json"
        if registry_path.is_file():
            try:
                active_sources = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
                active_path = active_sources.get(name)
                if isinstance(active_path, str) and (PROJECT_ROOT / active_path).is_file():
                    data["file_location"] = active_path
            except (OSError, yaml.YAMLError):
                pass
        return data

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        query_terms = {part.lower() for part in query.replace("-", " ").split() if len(part) > 2}
        entries: list[dict[str, Any]] = []
        files = [
            "index.yaml",
            "relationships.yaml",
            "formulas.yaml",
            "business_rules.yaml",
            "analysis_patterns.yaml",
            "report_templates.yaml",
            "examples.yaml",
            "datasets/orders.yaml",
            "datasets/machines.yaml",
            "datasets/inventory.yaml",
            "business_terms/order_terms.yaml",
            "business_terms/machine_terms.yaml",
            "business_terms/inventory_terms.yaml",
        ]
        for relative in files:
            data = self.load_yaml(relative)
            text = yaml.safe_dump(data, sort_keys=False).lower()
            score = sum(1 for term in query_terms if term in text)
            if score:
                entries.append({"path": relative, "score": score, "content": data})
        entries.extend(FactoryWiki().search(query, limit=limit))
        return sorted(entries, key=lambda item: item["score"], reverse=True)[:limit]

    def relevant_datasets(self, query: str) -> list[str]:
        lowered = query.lower()
        datasets = []
        if any(re.search(rf"\b{word}\b", lowered) for word in ["order", "orders", "delayed", "due", "priority", "complete", "ready"]):
            datasets.append("orders")
        if any(re.search(rf"\b{word}\b", lowered) for word in ["machine", "machines", "capacity", "idle", "efficiency", "utilization", "unavailable", "maintenance"]):
            datasets.append("machines")
        if any(re.search(rf"\b{word}\b", lowered) for word in ["inventory", "material", "materials", "stock", "stocks", "reorder", "shortage", "shortages"]):
            datasets.append("inventory")
        if any(re.search(rf"\b{word}\b", lowered) for word in ["working", "running"]):
            datasets.append("machines")
        return datasets or ["orders", "machines", "inventory"]
