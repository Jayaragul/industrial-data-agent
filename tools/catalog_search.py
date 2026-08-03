from __future__ import annotations

from agent.catalog_context import Catalog


def catalog_search(catalog: Catalog, query: str, limit: int = 8) -> list[dict[str, object]]:
    return catalog.search(query, limit)
