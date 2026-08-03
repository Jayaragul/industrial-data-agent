from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from agent.models import PROJECT_ROOT
from agent.catalog_context import Catalog
from harness.permissions import ensure_runtime_dirs
from sandbox.code_validator import GeneratedCodeValidator
from sandbox.resource_limits import cpu_limit, memory_limit_mb, sandbox_timeout_seconds
from sandbox.result_validator import SandboxResultValidator


class SandboxRunner:
    def prepare_filesystem(self, request_id: str, datasets: list[str]) -> tuple[Path, Path, Path]:
        ensure_runtime_dirs()
        input_dir = PROJECT_ROOT / "runtime" / "sandbox_inputs" / request_id
        work_dir = PROJECT_ROOT / "runtime" / "sandbox_work" / request_id
        output_dir = PROJECT_ROOT / "runtime" / "outputs" / request_id
        input_dir.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        catalog = Catalog()
        for dataset in datasets:
            source = PROJECT_ROOT / catalog.dataset(dataset)["file_location"]
            if not source.exists():
                raise ValueError(f"missing input dataset: {dataset}")
            shutil.copy2(source, input_dir / source.name)
        return input_dir, work_dir, output_dir

    def execute(self, request_id: str, code: str, datasets: list[str]) -> dict[str, object]:
        validation = GeneratedCodeValidator().validate(code)
        if not validation.ok:
            return {"status": "validation_failed", "validation": validation.to_dict()}

        input_dir, work_dir, output_dir = self.prepare_filesystem(request_id, datasets)
        code_path = work_dir / "analysis.py"
        code_path.write_text(code, encoding="utf-8")
        started = time.monotonic()

        if os.getenv("INDUSTRIAL_AGENT_ALLOW_LOCAL_SANDBOX", "false").lower() == "true":
            env = {"PYTHONPATH": "", "MPLBACKEND": "Agg"}
            local_code = code.replace("/sandbox/input", input_dir.as_posix())
            local_code = local_code.replace("/sandbox/work", work_dir.as_posix())
            local_code = local_code.replace("/sandbox/output", output_dir.as_posix())
            code_path.write_text(local_code, encoding="utf-8")
            proc = subprocess.run(["python", str(code_path)], timeout=sandbox_timeout_seconds(), capture_output=True, text=True, env=env)
        elif shutil.which("docker"):
            command = [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--cpus",
                cpu_limit(),
                "--memory",
                f"{memory_limit_mb()}m",
                "--pids-limit",
                "64",
                "--read-only",
                "--security-opt",
                "no-new-privileges",
                "-v",
                f"{input_dir}:/sandbox/input:ro",
                "-v",
                f"{work_dir}:/sandbox/work:rw",
                "-v",
                f"{output_dir}:/sandbox/output:rw",
                "industrial-data-agent-sandbox",
                "python",
                "/sandbox/work/analysis.py",
            ]
            proc = subprocess.run(command, timeout=sandbox_timeout_seconds(), capture_output=True, text=True)
        else:
            return {
                "status": "sandbox_unavailable",
                "validation": validation.to_dict(),
                "error": "Docker sandbox image is required for generated code execution.",
            }

        elapsed = time.monotonic() - started
        if proc.returncode != 0:
            return {
                "status": "execution_failed",
                "validation": validation.to_dict(),
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "execution_time": elapsed,
                "output_dir": str(output_dir),
            }
        result = SandboxResultValidator().validate(output_dir)
        return {
            "status": "success",
            "validation": validation.to_dict(),
            "result": result.model_dump(),
            "execution_time": elapsed,
            "output_dir": str(output_dir),
        }
