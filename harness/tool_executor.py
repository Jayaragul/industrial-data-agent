from __future__ import annotations

from typing import Any

from harness.tool_registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def execute(self, function_name: str, arguments: dict[str, Any]) -> Any:
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        return self.registry.call(function_name, **arguments)
