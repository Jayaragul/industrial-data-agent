from __future__ import annotations


def normalize_status(value: object) -> str:
    return str(value or "").strip().upper()
