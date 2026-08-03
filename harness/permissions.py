from __future__ import annotations

from pathlib import Path

from agent.models import PROJECT_ROOT

APPROVED_HOST_DIRS = [
    PROJECT_ROOT / "data" / "input",
    PROJECT_ROOT / "runtime" / "sandbox_inputs",
    PROJECT_ROOT / "runtime" / "sandbox_work",
    PROJECT_ROOT / "runtime" / "outputs",
    PROJECT_ROOT / "runtime" / "logs",
    PROJECT_ROOT / "runtime" / "audit",
    PROJECT_ROOT / "runtime" / "cache",
]


def ensure_runtime_dirs() -> None:
    for path in APPROVED_HOST_DIRS:
        path.mkdir(parents=True, exist_ok=True)


def is_inside(child: Path, parent: Path) -> bool:
    child_resolved = child.resolve()
    parent_resolved = parent.resolve()
    return child_resolved == parent_resolved or parent_resolved in child_resolved.parents


def reject_unsafe_path_text(value: str) -> None:
    lowered = value.lower()
    unsafe = ["../", "..\\", "~", "c:\\", "d:\\", "/home/", "/tmp/", "file://"]
    if any(marker in lowered for marker in unsafe):
        raise ValueError("unsafe path text rejected")
