from __future__ import annotations

import json
import mimetypes
import re
import shutil
from pathlib import Path
from uuid import uuid4

from .models import NoteEvent, Project, StoredFile, safe_title, utc_now


class ProjectNotFoundError(KeyError):
    pass


class ProjectStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.projects_root = self.root / "projects"
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def create_project(self, filename: str, content: bytes) -> Project:
        if not content:
            raise ValueError("uploaded file is empty")

        project_id = uuid4().hex[:12]
        project_dir = self._project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=False)

        source_name = self._source_name(filename)
        source_path = project_dir / source_name
        source_path.write_bytes(content)

        media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        now = utc_now()
        project = Project(
            id=project_id,
            title=safe_title(filename),
            original_filename=filename,
            status="uploaded",
            created_at=now,
            updated_at=now,
            source_audio=StoredFile(name=source_name, path=source_name, media_type=media_type),
        )
        self.save_project(project)
        return project

    def get_project(self, project_id: str) -> Project:
        metadata_path = self._metadata_path(project_id)
        if not metadata_path.exists():
            raise ProjectNotFoundError(project_id)
        return Project.model_validate_json(metadata_path.read_text(encoding="utf-8"))

    def save_project(self, project: Project) -> Project:
        project = project.with_updated_timestamp()
        project_dir = self._project_dir(project.id)
        project_dir.mkdir(parents=True, exist_ok=True)
        self._metadata_path(project.id).write_text(
            json.dumps(project.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return project

    def replace_notes(self, project_id: str, notes: list[NoteEvent]) -> Project:
        project = self.get_project(project_id)
        sorted_notes = sorted(notes, key=lambda note: (note.start_sec, note.pitch, note.end_sec))
        return self.save_project(project.model_copy(update={"notes": sorted_notes, "status": "edited"}))

    def source_audio_path(self, project_id: str) -> Path:
        project = self.get_project(project_id)
        return self._project_dir(project_id) / project.source_audio.path

    def project_file_path(self, project_id: str, relative_path: str) -> Path:
        target = (self._project_dir(project_id) / relative_path).resolve()
        project_dir = self._project_dir(project_id).resolve()
        try:
            target.relative_to(project_dir)
        except ValueError as error:
            raise ValueError("project file path escapes project directory") from error
        return target

    def copy_source_to_project_file(self, project_id: str, relative_path: str) -> None:
        shutil.copyfile(self.source_audio_path(project_id), self.project_file_path(project_id, relative_path))

    def _project_dir(self, project_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{12}", project_id):
            raise ProjectNotFoundError(project_id)
        return self.projects_root / project_id

    def _metadata_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "project.json"

    @staticmethod
    def _source_name(filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        if not suffix or len(suffix) > 12:
            suffix = ".audio"
        return f"source{suffix}"
