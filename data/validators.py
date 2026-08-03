from __future__ import annotations


def require_columns(columns: set[str], required: set[str]) -> None:
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"missing required columns: {', '.join(missing)}")
