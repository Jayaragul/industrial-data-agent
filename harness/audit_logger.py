from __future__ import annotations

import json

from agent.models import AuditRecord, PROJECT_ROOT
from harness.permissions import ensure_runtime_dirs


class AuditLogger:
    def save(self, record: AuditRecord) -> None:
        ensure_runtime_dirs()
        path = PROJECT_ROOT / "runtime" / "audit" / f"{record.request_id}.json"
        path.write_text(json.dumps(record.model_dump(), indent=2, default=str), encoding="utf-8")
