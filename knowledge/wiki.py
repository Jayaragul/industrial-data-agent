from __future__ import annotations

import csv
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.models import PROJECT_ROOT


class FactoryWiki:
    """Maintains a factual, searchable wiki around the immutable uploaded sources."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or PROJECT_ROOT / "runtime" / "factory_wiki"
        self.raw_root = self.root / "raw"
        self.pages_root = self.root / "pages" / "datasets"
        self.index_path = self.root / "index.md"
        self.log_path = self.root / "log.md"
        self.schema_path = self.root / "HARNESS.md"

    def ingest(self, dataset: str, source: Path, active_copy: Path) -> Path:
        self._ensure_layout()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive_dir = self.raw_root / dataset
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive = archive_dir / f"{timestamp}_{source.name}"
        shutil.copy2(source, archive)
        rows = self._read_rows(active_copy)
        page = self.pages_root / f"{dataset}.md"
        page.write_text(self._dataset_page(dataset, rows, archive), encoding="utf-8")
        self._write_index()
        self._append_log(f"ingest | {dataset} | {len(rows)} records | source: {archive.relative_to(self.root).as_posix()}")
        return page

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        if not self.index_path.is_file():
            return []
        terms = {term for term in query.lower().replace("-", " ").split() if len(term) > 2}
        entries: list[dict[str, Any]] = []
        for page in self.pages_root.glob("*.md"):
            content = page.read_text(encoding="utf-8")
            score = sum(term in content.lower() for term in terms)
            if score:
                entries.append({"path": f"factory_wiki/{page.relative_to(self.root).as_posix()}", "score": score, "content": content})
        return sorted(entries, key=lambda item: item["score"], reverse=True)[:limit]

    def lint(self) -> list[str]:
        if not self.index_path.is_file():
            return ["The wiki has no uploaded data yet."]
        expected = {f"{name}.md" for name in ("orders", "machines", "inventory")}
        present = {path.name for path in self.pages_root.glob("*.md")}
        messages = [f"Missing wiki page: {name}" for name in sorted(expected - present)]
        if not self.log_path.is_file() or not self.log_path.read_text(encoding="utf-8").strip():
            messages.append("The wiki activity log is empty.")
        return messages or ["Wiki health check passed."]

    def record_query(self, question: str, intent: str) -> None:
        if not self.index_path.is_file():
            return
        compact_question = " ".join(question.split())[:240]
        self._append_log(f"query | {intent} | {compact_question}")

    def _ensure_layout(self) -> None:
        self.raw_root.mkdir(parents=True, exist_ok=True)
        self.pages_root.mkdir(parents=True, exist_ok=True)
        if not self.schema_path.exists():
            self.schema_path.write_text(
                "# Factory Wiki Harness\n\nRaw sources are immutable. Dataset pages are maintained from validated active data. "
                "Use the wiki for context and provenance; use validated CSV rows for quantities, counts, and dates.\n",
                encoding="utf-8",
            )

    def _read_rows(self, path: Path) -> list[dict[str, str]]:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def _dataset_page(self, dataset: str, rows: list[dict[str, str]], archive: Path) -> str:
        columns = list(rows[0]) if rows else []
        examples = [row.get(columns[0], "") for row in rows[:5]] if columns else []
        return "\n".join([
            f"# {dataset.title()} Dataset",
            "",
            f"- Records: {len(rows)}",
            f"- Source archive: `{archive.relative_to(self.root).as_posix()}`",
            f"- Columns: {', '.join(columns)}",
            f"- Example record IDs: {', '.join(examples) or 'none'}",
            "",
            "This page is generated from validated uploaded data. Numeric answers must be checked against the active CSV dataset.",
            "",
        ])

    def _write_index(self) -> None:
        pages = sorted(self.pages_root.glob("*.md"))
        lines = ["# Factory Wiki Index", "", "Persistent context built from validated uploaded datasets.", ""]
        for page in pages:
            content = page.read_text(encoding="utf-8").splitlines()
            record_line = next((line for line in content if line.startswith("- Records:")), "- Records: unknown")
            lines.append(f"- [Dataset: {page.stem}](pages/datasets/{page.name}) - {record_line.removeprefix('- ')}")
        self.index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _append_log(self, message: str) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"## [{datetime.now(timezone.utc).date().isoformat()}] {message}\n")
