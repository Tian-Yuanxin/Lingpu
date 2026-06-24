from __future__ import annotations

import importlib.util
import mimetypes
import math
import os
import re
import shutil
import subprocess
import sys
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .models import EngineInfo, NoteEvent, Project, ScoreSettings, Stem, StoredFile
from .store import ProjectStore
from .transcription import import_transcription_notes


CommandRunner = Callable[[list[str], Path, int], tuple[int, str, str]]
DEFAULT_COMMAND_TIMEOUT_SECONDS = 60 * 60
SUPPORTED_AUDIO_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class EngineDefinition:
    id: str
    label: str
    kind: str
    detail: str


class EngineRegistry:
    def __init__(self, detectors: dict[str, bool] | None = None):
        self.detectors = detectors or {}

    def list_engines(self) -> list[EngineInfo]:
        return [
            EngineInfo(
                id=definition.id,
                label=definition.label,
                kind=definition.kind,
                available=self.is_available(definition.id),
                detail=definition.detail,
            )
            for definition in ENGINE_DEFINITIONS
        ]

    def get(self, engine_id: str, kind: str) -> EngineInfo:
        for engine in self.list_engines():
            if engine.id == engine_id and engine.kind == kind:
                return engine
        raise ValueError(f"unknown engine: {engine_id}")

    def is_available(self, engine_id: str) -> bool:
        if engine_id in self.detectors:
            return self.detectors[engine_id]
        if engine_id in {"local-fallback", "local-placeholder"}:
            return True
        if engine_id == "audio-separator":
            return _has_module("audio_separator") or _has_executable("audio-separator")
        if engine_id == "demucs":
            return _has_executable("demucs") or _has_module("demucs")
        if engine_id == "uvr":
            return _has_executable("audio-separator") or _has_executable("uvr")
        if engine_id == "basic-pitch":
            return _has_module("basic_pitch") or _has_executable("basic-pitch")
        if engine_id == "omnizart":
            return _has_module("omnizart") or _has_executable("omnizart")
        if engine_id == "mt3":
            return _has_module("mt3") or _has_executable("mt3")
        return False


ENGINE_DEFINITIONS = [
    EngineDefinition(
        id="local-fallback",
        label="Original mix fallback",
        kind="separation",
        detail="Uses the uploaded audio as one stem. Always available for offline editing and export.",
    ),
    EngineDefinition(
        id="demucs",
        label="Demucs",
        kind="separation",
        detail="External stem separation command or Python module. Best first target for vocals/drums/bass/other.",
    ),
    EngineDefinition(
        id="uvr",
        label="UVR / MDX models",
        kind="separation",
        detail="External UVR-compatible separation command. Useful for vocal/instrumental and MDX model variants.",
    ),
    EngineDefinition(
        id="audio-separator",
        label="audio-separator",
        kind="separation",
        detail="Python/CLI wrapper around UVR-style separation models.",
    ),
    EngineDefinition(
        id="local-placeholder",
        label="Editable placeholder",
        kind="transcription",
        detail="Generates deterministic note events from duration. Always available for UI and export work.",
    ),
    EngineDefinition(
        id="basic-pitch",
        label="Basic Pitch",
        kind="transcription",
        detail="Audio-to-MIDI transcription for one prominent instrument or separated stem.",
    ),
    EngineDefinition(
        id="omnizart",
        label="Omnizart",
        kind="transcription",
        detail="Optional transcription toolkit for melody, vocal, drum, chord, beat, and instrument tasks.",
    ),
    EngineDefinition(
        id="mt3",
        label="MT3",
        kind="transcription",
        detail="Research-grade multi-instrument transcription adapter target.",
    ),
]


class ProcessingService:
    def __init__(
        self,
        store: ProjectStore,
        registry: EngineRegistry | None = None,
        command_runner: CommandRunner | None = None,
    ):
        self.store = store
        self.registry = registry or EngineRegistry()
        self.command_runner = command_runner or self._run_command

    def list_engines(self) -> list[EngineInfo]:
        return self.registry.list_engines()

    def separate(self, project_id: str, engine_id: str = "local-fallback") -> Project:
        project = self.store.get_project(project_id)
        engine = self.registry.get(engine_id, kind="separation")

        if engine.available and engine.id == "local-fallback":
            message = "Using original mix as the editable source stem."
        elif engine.available and engine.id == "demucs":
            return self._separate_with_demucs(project, engine)
        elif engine.available and engine.id == "audio-separator":
            return self._separate_with_audio_separator(project, engine)
        elif engine.available:
            message = f"{engine.label} is available. External execution adapter is ready to be wired for real stems."
        else:
            message = f"{engine.label} is not available. Using original mix as a fallback stem."

        return self._save_fallback_stem(project, engine=engine.id, message=message)

    def transcribe(self, project_id: str, stem_id: str, engine_id: str = "local-placeholder") -> Project:
        project = self.store.get_project(project_id)
        stem = next((candidate for candidate in project.stems if candidate.id == stem_id), None)
        if stem is None:
            raise ValueError(f"unknown stem: {stem_id}")

        engine = self.registry.get(engine_id, kind="transcription")
        audio_path = self.store.project_file_path(project.id, stem.audio.path)

        if engine.available and engine.id == "local-placeholder":
            notes = self._fallback_notes(audio_path)
            message = "Generated editable placeholder notes."
        elif engine.available and engine.id == "basic-pitch":
            return self._transcribe_with_basic_pitch(project, stem, audio_path, engine)
        elif engine.available:
            notes = self._fallback_notes(audio_path)
            message = f"{engine.label} is available. External execution adapter is ready to replace fallback notes."
        else:
            notes = self._fallback_notes(audio_path)
            message = f"{engine.id} is not available. Generated fallback editable notes."

        return self._save_transcription(project, notes, message)

    def _source_stem(self, project: Project, engine: str) -> Stem:
        return Stem(
            id="source",
            label="Original mix",
            audio=StoredFile(
                name=project.source_audio.name,
                path=project.source_audio.path,
                media_type=project.source_audio.media_type,
            ),
            engine=engine,
        )

    def _separate_with_demucs(self, project: Project, engine: EngineInfo) -> Project:
        project_dir = self.store.project_file_path(project.id, "")
        source_path = self.store.source_audio_path(project.id)
        output_root = project_dir / "separation" / "demucs"
        output_root.parent.mkdir(parents=True, exist_ok=True)

        command = [
            _python_executable(),
            "-m",
            "lingpu.demucs_runner",
            "-d",
            os.environ.get("LINGPU_DEMUCS_DEVICE", "cpu"),
            "-o",
            str(output_root),
            str(source_path),
        ]
        failed = self._run_separation_command(command, project_dir, engine.label)
        if failed is not None:
            return self._save_fallback_stem(project, engine=engine.id, message=failed)

        stems = self._generated_stems(project, engine.id, output_root)
        if not stems:
            message = "Demucs did not produce supported audio stems. Using original mix as a fallback stem."
            return self._save_fallback_stem(project, engine=engine.id, message=message)

        return self._save_generated_stems(project, stems, f"Demucs separated {len(stems)} stems.")

    def _separate_with_audio_separator(self, project: Project, engine: EngineInfo) -> Project:
        project_dir = self.store.project_file_path(project.id, "")
        source_path = self.store.source_audio_path(project.id)
        output_root = project_dir / "separation" / "audio-separator"
        model_dir = self.store.root / "models" / "audio-separator"
        output_root.parent.mkdir(parents=True, exist_ok=True)
        model_dir.mkdir(parents=True, exist_ok=True)

        command = [
            _tool_path("audio-separator", "LINGPU_AUDIO_SEPARATOR_BIN") or "audio-separator",
            str(source_path),
            "--model_filename",
            os.environ.get("LINGPU_AUDIO_SEPARATOR_MODEL", "model_bs_roformer_ep_317_sdr_12.9755.ckpt"),
            "--output_dir",
            str(output_root),
            "--model_file_dir",
            str(model_dir),
            "--output_format",
            "WAV",
        ]
        failed = self._run_separation_command(command, project_dir, engine.label)
        if failed is not None:
            return self._save_fallback_stem(project, engine=engine.id, message=failed)

        stems = self._generated_stems(project, engine.id, output_root)
        if not stems:
            message = "audio-separator did not produce supported audio stems. Using original mix as a fallback stem."
            return self._save_fallback_stem(project, engine=engine.id, message=message)

        return self._save_generated_stems(project, stems, f"audio-separator separated {len(stems)} stems.")

    def _transcribe_with_basic_pitch(
        self,
        project: Project,
        stem: Stem,
        audio_path: Path,
        engine: EngineInfo,
    ) -> Project:
        project_dir = self.store.project_file_path(project.id, "")
        output_root = project_dir / "transcription" / "basic-pitch" / stem.id
        output_root.parent.mkdir(parents=True, exist_ok=True)

        command = [
            _tool_path("basic-pitch", "LINGPU_BASIC_PITCH_BIN") or "basic-pitch",
            str(output_root),
            str(audio_path),
            "--save-note-events",
        ]
        failed = self._run_transcription_command(command, project_dir, engine.label)
        if failed is not None:
            return self._save_transcription(project, self._fallback_notes(audio_path), failed)

        notes = import_transcription_notes(output_root)
        if not notes:
            message = "Basic Pitch did not produce importable notes. Generated fallback editable notes."
            return self._save_transcription(project, self._fallback_notes(audio_path), message)

        return self._save_transcription(project, notes, f"Basic Pitch imported {len(notes)} notes.")

    def _run_separation_command(self, command: list[str], cwd: Path, label: str) -> str | None:
        try:
            return_code, stdout, stderr = self.command_runner(
                command,
                cwd,
                DEFAULT_COMMAND_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            return f"{label} command was not found. Using original mix as a fallback stem."
        except subprocess.TimeoutExpired:
            return f"{label} timed out. Using original mix as a fallback stem."

        if return_code == 0:
            return None

        detail = _last_output_line(stderr or stdout)
        if detail:
            return f"{label} failed with exit code {return_code}: {detail}. Using original mix as a fallback stem."
        return f"{label} failed with exit code {return_code}. Using original mix as a fallback stem."

    def _run_transcription_command(self, command: list[str], cwd: Path, label: str) -> str | None:
        try:
            return_code, stdout, stderr = self.command_runner(
                command,
                cwd,
                DEFAULT_COMMAND_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            return f"{label} command was not found. Generated fallback editable notes."
        except subprocess.TimeoutExpired:
            return f"{label} timed out. Generated fallback editable notes."

        if return_code == 0:
            return None

        detail = _last_output_line(stderr or stdout)
        if detail:
            return f"{label} failed with exit code {return_code}: {detail}. Generated fallback editable notes."
        return f"{label} failed with exit code {return_code}. Generated fallback editable notes."

    def _generated_stems(self, project: Project, engine: str, output_root: Path) -> list[Stem]:
        project_dir = self.store.project_file_path(project.id, "").resolve()
        audio_paths = sorted(
            path
            for path in output_root.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_SUFFIXES
        )
        stems: list[Stem] = []
        seen_ids: dict[str, int] = {}

        for audio_path in audio_paths:
            stem_id = _unique_stem_id(_stem_id_from_audio_path(audio_path), seen_ids)
            relative_path = audio_path.resolve().relative_to(project_dir).as_posix()
            stems.append(
                Stem(
                    id=stem_id,
                    label=_stem_label(stem_id),
                    audio=StoredFile(
                        name=audio_path.name,
                        path=relative_path,
                        media_type=mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream",
                    ),
                    engine=engine,
                )
            )

        return stems

    def _save_fallback_stem(self, project: Project, engine: str, message: str) -> Project:
        stem = self._source_stem(project, engine=engine)
        updated = project.model_copy(update={"status": "separated", "stems": [stem], "message": message})
        return self.store.save_project(updated)

    def _save_generated_stems(self, project: Project, stems: list[Stem], message: str) -> Project:
        updated = project.model_copy(update={"status": "separated", "stems": stems, "message": message})
        return self.store.save_project(updated)

    def _save_transcription(self, project: Project, notes: list[NoteEvent], message: str) -> Project:
        updated = project.model_copy(
            update={
                "status": "transcribed",
                "notes": notes,
                "score_settings": ScoreSettings(),
                "message": message,
            }
        )
        return self.store.save_project(updated)

    @staticmethod
    def _run_command(command: list[str], cwd: Path, timeout_seconds: int) -> tuple[int, str, str]:
        _add_static_ffmpeg_to_path()
        env = os.environ.copy()
        env["PATH"] = os.pathsep.join([*(_local_bin_dirs()), env.get("PATH", "")])
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            env=env,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return completed.returncode, completed.stdout, completed.stderr

    @staticmethod
    def _fallback_notes(audio_path: Path) -> list[NoteEvent]:
        duration = max(_audio_duration_seconds(audio_path), 1.0)
        note_count = max(4, min(16, math.ceil(duration / 0.25)))
        step = max(duration / note_count, 0.125)
        scale = [60, 62, 64, 65, 67, 69, 71, 72]
        notes: list[NoteEvent] = []

        for index in range(note_count):
            start = round(index * step, 3)
            end = round(min(duration, start + step * 0.86), 3)
            if end <= start:
                end = round(start + 0.1, 3)
            notes.append(
                NoteEvent(
                    pitch=scale[index % len(scale)],
                    start_sec=start,
                    end_sec=end,
                    velocity=88,
                    confidence=0.35,
                )
            )
        return notes


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _has_executable(name: str) -> bool:
    return _tool_path(name) is not None


def _tool_path(name: str, env_var: str | None = None) -> str | None:
    configured = os.environ.get(env_var) if env_var else None
    if configured:
        return configured

    for scripts_dir in _local_bin_paths():
        for suffix in [".exe", ".cmd", ".bat", ""]:
            candidate = scripts_dir / f"{name}{suffix}"
            if candidate.exists():
                return str(candidate)

    return shutil.which(name)


def _python_executable() -> str:
    configured = os.environ.get("LINGPU_PYTHON_BIN")
    if configured:
        return configured

    for candidate in [PROJECT_ROOT / ".venv" / "Scripts" / "python.exe", PROJECT_ROOT / ".venv" / "bin" / "python"]:
        if candidate.exists():
            return str(candidate)

    return sys.executable


def _local_bin_paths() -> list[Path]:
    return [PROJECT_ROOT / ".venv" / "Scripts", PROJECT_ROOT / ".venv" / "bin"]


def _local_bin_dirs() -> list[str]:
    return [str(path) for path in _local_bin_paths() if path.exists()]


def _add_static_ffmpeg_to_path() -> None:
    try:
        import static_ffmpeg
    except ImportError:
        return
    static_ffmpeg.add_paths(weak=True)


def _last_output_line(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[-1][:240]


def _stem_id_from_audio_path(audio_path: Path) -> str:
    match = re.search(r"\(([^)]+)\)", audio_path.stem)
    raw_id = match.group(1) if match else audio_path.stem
    normalized = re.sub(r"[^a-z0-9_-]+", "_", raw_id.lower()).strip("_-")
    return normalized or "stem"


def _unique_stem_id(stem_id: str, seen_ids: dict[str, int]) -> str:
    count = seen_ids.get(stem_id, 0)
    seen_ids[stem_id] = count + 1
    if count == 0:
        return stem_id
    return f"{stem_id}-{count + 1}"


def _stem_label(stem_id: str) -> str:
    return stem_id.replace("_", " ").replace("-", " ").title()


def _audio_duration_seconds(audio_path: Path) -> float:
    if audio_path.suffix.lower() != ".wav":
        return 8.0
    try:
        with wave.open(str(audio_path), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            return frames / float(rate) if rate else 8.0
    except (wave.Error, OSError):
        return 8.0
