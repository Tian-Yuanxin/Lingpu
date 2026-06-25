from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .exporters import ExportService
from .models import NotesPatch, Project, ScoreSettings, SeparateRequest, TranscribeRequest
from .processing import ProcessingService
from .store import ProjectNotFoundError, ProjectStore


def create_app(storage_root: str | Path | None = None) -> FastAPI:
    root = Path(storage_root or os.environ.get("LINGPU_STORAGE", "data")).resolve()
    store = ProjectStore(root)
    processing = ProcessingService(store)
    exports = ExportService(store)

    app = FastAPI(title="Lingpu", version="0.1.0")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/engines")
    def list_engines():
        return jsonable_encoder(processing.list_engines(), by_alias=True)

    @app.post("/api/projects", status_code=201)
    async def create_project(file: UploadFile = File(...)):
        content = await file.read()
        try:
            project = store.create_project(file.filename or "audio.wav", content)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _project_response(project)

    @app.get("/api/projects")
    def list_projects():
        return jsonable_encoder(store.list_projects(), by_alias=True)

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str):
        return _project_response(store.get_project(project_id))

    @app.patch("/api/projects/{project_id}/score-settings")
    def save_score_settings(project_id: str, score_settings: ScoreSettings):
        return _project_response(store.save_score_settings(project_id, score_settings))

    @app.post("/api/projects/{project_id}/separate")
    def separate_project(project_id: str, request: SeparateRequest | None = None):
        try:
            project = processing.separate(project_id, engine_id=(request.engine_id if request else "local-fallback"))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _project_response(project)

    @app.post("/api/projects/{project_id}/transcribe")
    def transcribe_project(project_id: str, request: TranscribeRequest):
        try:
            project = processing.transcribe(project_id, request.stem_id, engine_id=request.engine_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _project_response(project)

    @app.patch("/api/projects/{project_id}/notes")
    def replace_notes(project_id: str, patch: NotesPatch):
        return _project_response(store.replace_notes(project_id, patch.notes))

    @app.get("/api/projects/{project_id}/files/{relative_path:path}")
    def get_project_file(project_id: str, relative_path: str):
        path = store.project_file_path(project_id, relative_path)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="file not found")
        return FileResponse(path)

    @app.get("/api/projects/{project_id}/export/{file_format}")
    def export_project(project_id: str, file_format: str):
        try:
            payload = exports.export_project(project_id, file_format)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return Response(
            content=payload.content,
            media_type=payload.media_type,
            headers={"Content-Disposition": f'attachment; filename="{payload.filename}"'},
        )

    @app.exception_handler(ProjectNotFoundError)
    async def project_not_found(_request, _error):
        return Response(content='{"detail":"project not found"}', media_type="application/json", status_code=404)

    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app


def _project_response(project: Project):
    return jsonable_encoder(project, by_alias=True)
