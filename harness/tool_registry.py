from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, function: Callable[..., Any]) -> None:
        if name in self._tools:
            raise ValueError(f"tool already registered: {name}")
        self._tools[name] = function

    def names(self) -> list[str]:
        return sorted(self._tools)

    def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise ValueError(f"unregistered tool: {name}")
        return self._tools[name](**kwargs)
