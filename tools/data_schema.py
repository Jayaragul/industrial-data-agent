from __future__ import annotations

from agent.catalog_context import Catalog
from data.repository import DatasetRepository


def data_schema(catalog: Catalog, dataset: str) -> dict[str, object]:
    return DatasetRepository(catalog).get_schema(dataset)
