from __future__ import annotations

from pathlib import Path

from agent.models import PROJECT_ROOT
from harness.permissions import is_inside
from sandbox.resource_limits import max_output_file_size_mb


def register_generated_file(request_id: str, relative_path: str, file_type: str) -> dict[str, object]:
    output_dir = PROJECT_ROOT / "runtime" / "outputs" / request_id
    path = (output_dir / relative_path).resolve()
    if not is_inside(path, output_dir):
        raise ValueError("generated file escapes request output directory")
    if not path.exists():
        raise ValueError("generated file does not exist")
    if path.stat().st_size > max_output_file_size_mb() * 1024 * 1024:
        raise ValueError("generated file exceeds size limit")
    allowed = {"csv": ".csv", "pdf": ".pdf", "json": ".json", "chart": ".png"}
    if file_type not in allowed:
        raise ValueError("unsupported file type")
    return {"path": str(path.relative_to(PROJECT_ROOT)), "type": file_type, "size_bytes": path.stat().st_size}
