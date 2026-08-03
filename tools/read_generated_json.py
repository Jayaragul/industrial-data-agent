from __future__ import annotations

import json
from pathlib import Path

from agent.models import PROJECT_ROOT
from harness.permissions import is_inside


def read_generated_json(request_id: str, relative_path: str) -> object:
    output_dir = PROJECT_ROOT / "runtime" / "outputs" / request_id
    path = (output_dir / relative_path).resolve()
    if not is_inside(path, output_dir) or path.suffix.lower() != ".json":
        raise ValueError("only request-owned JSON outputs may be read")
    return json.loads(path.read_text(encoding="utf-8"))
