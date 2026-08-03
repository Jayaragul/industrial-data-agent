from __future__ import annotations

from sandbox.runner import SandboxRunner


def sandbox_execute_python(request_id: str, code: str, datasets: list[str], requested_outputs: list[str] | None = None) -> dict[str, object]:
    return SandboxRunner().execute(request_id=request_id, code=code, datasets=datasets)
