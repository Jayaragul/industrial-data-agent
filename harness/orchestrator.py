from __future__ import annotations

from agent.catalog_context import Catalog
from data.repository import DatasetRepository
from harness.tool_registry import ToolRegistry
from tools.catalog_search import catalog_search
from tools.catalog_data import aggregate_dataset, describe_dataset, get_column_statistics, get_distinct_values, list_datasets, preview_dataset, query_dataset
from tools.data_preview import data_preview
from tools.data_schema import data_schema
from tools.read_generated_json import read_generated_json
from tools.register_generated_file import register_generated_file
from tools.sandbox_execute_python import sandbox_execute_python
from tools.validate_sandbox_result import validate_sandbox_result


def build_tool_registry(catalog: Catalog | None = None) -> ToolRegistry:
    catalog = catalog or Catalog()
    repository = DatasetRepository(catalog)
    registry = ToolRegistry()
    registry.register("catalog_search", lambda query, limit=8: catalog_search(catalog, query, limit))
    registry.register("data_preview", data_preview)
    registry.register("data_schema", lambda dataset: data_schema(catalog, dataset))
    registry.register("list_datasets", lambda: list_datasets(repository))
    registry.register("describe_dataset", lambda dataset: describe_dataset(repository, dataset))
    registry.register("preview_dataset", lambda dataset, limit=5: preview_dataset(repository, dataset, limit))
    registry.register("get_distinct_values", lambda dataset, field, limit=50: get_distinct_values(repository, dataset, field, limit))
    registry.register("get_column_statistics", lambda dataset, fields: get_column_statistics(repository, dataset, fields))
    registry.register("query_dataset", lambda dataset, filters=None, columns=None, limit=100: query_dataset(repository, dataset, filters, columns, limit))
    registry.register("aggregate_dataset", lambda dataset, field, operation, filters=None: aggregate_dataset(repository, dataset, field, operation, filters))
    registry.register("sandbox_execute_python", sandbox_execute_python)
    registry.register("validate_sandbox_result", validate_sandbox_result)
    registry.register("register_generated_file", register_generated_file)
    registry.register("read_generated_json", read_generated_json)
    registry.register("generate_final_response", lambda **kwargs: kwargs)
    return registry
