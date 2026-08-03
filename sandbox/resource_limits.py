from __future__ import annotations

import os


def sandbox_timeout_seconds() -> int:
    return int(os.getenv("SANDBOX_TIMEOUT_SECONDS", "30") or 30)


def memory_limit_mb() -> int:
    return int(os.getenv("SANDBOX_MEMORY_LIMIT_MB", "512") or 512)


def cpu_limit() -> str:
    return os.getenv("SANDBOX_CPU_LIMIT", "1") or "1"


def max_output_file_size_mb() -> int:
    return int(os.getenv("MAX_OUTPUT_FILE_SIZE_MB", "25") or 25)
