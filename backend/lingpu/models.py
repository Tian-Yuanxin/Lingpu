from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class AppModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StoredFile(AppModel):
    name: str
    path: str
    media_type: str = "application/octet-stream"


class Stem(AppModel):
    id: str
    label: str
    audio: StoredFile
    engine: str


class EngineInfo(AppModel):
    id: str
    label: str
    kind: Literal["separation", "transcription"]
    available: bool
    detail: str


MAJOR_KEY_SIGNATURES = {
    "Cb",
    "Gb",
    "Db",
    "Ab",
    "Eb",
    "Bb",
    "F",
    "C",
    "G",
    "D",
    "A",
    "E",
    "B",
    "F#",
    "C#",
}


class ScoreSettings(AppModel):
    tempo: int = Field(default=120, ge=40, le=240)
    time_signature: str = "4/4"
    key_signature: str = "C"
    quantization: Literal["1/4", "1/8", "1/16", "1/32"] = "1/16"

    @field_validator("time_signature")
    @classmethod
    def time_signature_must_be_supported(cls, value: str) -> str:
        parts = value.strip().split("/")
        if len(parts) != 2:
            raise ValueError("time_signature must use beats/beat-type format")
        try:
            beats = int(parts[0])
            beat_type = int(parts[1])
        except ValueError as error:
            raise ValueError("time_signature must use numeric values") from error
        if beats < 1 or beats > 32 or beat_type not in {2, 4, 8, 16}:
            raise ValueError("time_signature is not supported")
        return f"{beats}/{beat_type}"

    @field_validator("key_signature")
    @classmethod
    def key_signature_must_be_supported(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in MAJOR_KEY_SIGNATURES:
            raise ValueError("key_signature is not supported")
        return normalized


class NoteEvent(AppModel):
    pitch: int = Field(ge=0, le=127)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    velocity: int = Field(default=90, ge=1, le=127)
    confidence: float = Field(default=1.0, ge=0, le=1)

    @field_validator("end_sec")
    @classmethod
    def end_must_follow_start(cls, end_sec: float, info) -> float:
        start_sec = info.data.get("start_sec")
        if start_sec is not None and end_sec <= start_sec:
            raise ValueError("end_sec must be greater than start_sec")
        return end_sec


ProjectStatus = Literal["uploaded", "separated", "transcribed", "edited", "failed"]


class Project(AppModel):
    id: str
    title: str
    original_filename: str
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
    source_audio: StoredFile
    stems: list[Stem] = Field(default_factory=list)
    notes: list[NoteEvent] = Field(default_factory=list)
    score_settings: ScoreSettings = Field(default_factory=ScoreSettings)
    message: str | None = None

    def with_updated_timestamp(self) -> "Project":
        return self.model_copy(update={"updated_at": utc_now()})


class TranscribeRequest(AppModel):
    stem_id: str
    engine_id: str = "local-placeholder"


class SeparateRequest(AppModel):
    engine_id: str = "local-fallback"


class NotesPatch(AppModel):
    notes: list[NoteEvent]


def safe_title(filename: str) -> str:
    stem = Path(filename).stem.strip()
    return stem or "Untitled project"
