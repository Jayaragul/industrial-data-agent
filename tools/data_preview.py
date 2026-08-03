from __future__ import annotations

from data.repository import DatasetRepository


def data_preview(dataset: str, limit: int = 5) -> dict[str, object]:
    return DatasetRepository().preview(dataset, limit)
