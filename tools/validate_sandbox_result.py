from __future__ import annotations

from pathlib import Path

from sandbox.result_validator import SandboxResultValidator


def validate_sandbox_result(output_dir: str) -> dict[str, object]:
    result = SandboxResultValidator().validate(Path(output_dir))
    return result.model_dump()
