from __future__ import annotations

import csv
import json
from pathlib import Path

from agent.models import SandboxResult
from harness.permissions import is_inside
from sandbox.resource_limits import max_output_file_size_mb


class SandboxResultValidator:
    def validate(self, output_dir: Path) -> SandboxResult:
        result_path = output_dir / "result.json"
        if not result_path.exists():
            raise ValueError("missing result.json")
        result = SandboxResult.model_validate(json.loads(result_path.read_text(encoding="utf-8")))
        max_bytes = max_output_file_size_mb() * 1024 * 1024
        for generated in result.generated_files:
            path = Path(generated)
            if path.is_absolute() and str(path).startswith("/sandbox/output"):
                host_path = output_dir / path.relative_to("/sandbox/output")
            else:
                host_path = output_dir / path
            if not is_inside(host_path, output_dir):
                raise ValueError(f"generated file escapes output dir: {generated}")
            if not host_path.exists():
                raise ValueError(f"generated file is missing: {generated}")
            if host_path.stat().st_size > max_bytes:
                raise ValueError(f"generated file exceeds size limit: {generated}")
            suffix = host_path.suffix.lower()
            if suffix == ".csv":
                with host_path.open("r", newline="", encoding="utf-8") as handle:
                    reader = csv.reader(handle)
                    header = next(reader, None)
                    if not header:
                        raise ValueError(f"CSV has no header: {generated}")
            elif suffix == ".pdf":
                if host_path.read_bytes()[:4] != b"%PDF":
                    raise ValueError(f"invalid PDF signature: {generated}")
            elif suffix not in {".json", ".png", ".jpg", ".jpeg"}:
                raise ValueError(f"unsupported output extension: {generated}")
        if not result.evidence and result.summary.get("records_returned", 0):
            raise ValueError("evidence is required when records are returned")
        return result
