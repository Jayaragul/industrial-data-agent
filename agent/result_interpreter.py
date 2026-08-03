from __future__ import annotations

from pathlib import Path

from agent.models import PROJECT_ROOT, SandboxResult


def sandbox_file_paths(request_id: str, result: SandboxResult) -> list[str]:
    output_dir = PROJECT_ROOT / "runtime" / "outputs" / request_id
    paths: list[str] = []
    for value in result.generated_files:
        path = Path(value)
        if path.is_absolute() and str(path).startswith("/sandbox/output"):
            host_path = output_dir / path.relative_to("/sandbox/output")
        else:
            host_path = output_dir / value
        paths.append(str(host_path.relative_to(PROJECT_ROOT)))
    return paths
