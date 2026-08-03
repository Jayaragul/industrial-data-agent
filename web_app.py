from __future__ import annotations

import mimetypes
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from agent.models import PROJECT_ROOT
from agent.orchestrator import IndustrialDataAgent
from data.ingestion import DataIngestionService


app = FastAPI(title="Industrial Data Agent")
agent = IndustrialDataAgent()
ingestion = DataIngestionService(agent.catalog)
app.mount("/web", StaticFiles(directory=PROJECT_ROOT / "web"), name="web")


def dataset_status() -> list[dict[str, object]]:
    active = ingestion.active_sources()
    result = []
    for name in ("orders", "machines", "inventory"):
        schema = agent.catalog.dataset(name)
        path = PROJECT_ROOT / schema["file_location"]
        row_count = 0
        if path.is_file():
            try:
                import pandas as pd

                row_count = len(pd.read_csv(path))
            except Exception:
                row_count = 0
        result.append({
            "name": name,
            "label": name.title(),
            "active": name in active,
            "records": row_count,
            "source": "Uploaded file" if name in active else "Demo data",
        })
    return result


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")


@app.get("/api/status")
def status() -> dict[str, object]:
    return {
        "gemini_connected": agent.gemini.connected,
        "model": agent.gemini.model or "Not configured",
        "datasets": dataset_status(),
    }


@app.post("/api/ingest/{dataset}")
async def ingest(dataset: str, file: UploadFile = File(...)) -> dict[str, object]:
    if dataset not in {"orders", "machines", "inventory"}:
        raise HTTPException(status_code=400, detail="Choose Orders, Machines, or Inventory.")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(status_code=400, detail="Upload a CSV or Excel file.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        temporary_path = Path(handle.name)
        handle.write(await file.read())
    try:
        result = ingestion.ingest(dataset, temporary_path)
        return {"message": f"Loaded {result['records']} {dataset} records.", "status": dataset_status()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        temporary_path.unlink(missing_ok=True)


@app.get("/files/{file_path:path}")
def download(file_path: str) -> FileResponse:
    target = (PROJECT_ROOT / file_path).resolve()
    output_root = (PROJECT_ROOT / "runtime" / "outputs").resolve()
    if not str(target).startswith(str(output_root)) or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(target, media_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream", filename=target.name)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=False)
