import io
import math
import struct
import sys
import wave
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from lingpu.api import create_app


def make_wav_bytes(duration_seconds: float = 1.0, sample_rate: int = 8000) -> bytes:
    frames = []
    for index in range(int(duration_seconds * sample_rate)):
        sample = int(12000 * math.sin(2 * math.pi * 440 * index / sample_rate))
        frames.append(struct.pack("<h", sample))

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(frames))
    return buffer.getvalue()


def test_api_creates_processes_edits_and_exports_project(tmp_path):
    client = TestClient(create_app(storage_root=tmp_path))

    engines = client.get("/api/engines")
    assert engines.status_code == 200
    engine_ids = {engine["id"] for engine in engines.json()}
    assert {"demucs", "uvr", "basic-pitch", "omnizart", "mt3"}.issubset(engine_ids)

    created = client.post(
        "/api/projects",
        files={"file": ("demo.wav", make_wav_bytes(), "audio/wav")},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    separated = client.post(f"/api/projects/{project_id}/separate", json={"engineId": "local-fallback"})
    assert separated.status_code == 200
    assert separated.json()["stems"][0]["id"] == "source"
    assert separated.json()["stems"][0]["engine"] == "local-fallback"

    source_audio = client.get(f"/api/projects/{project_id}/files/source.wav")
    assert source_audio.status_code == 200
    assert source_audio.headers["content-type"].startswith("audio/")
    assert source_audio.content.startswith(b"RIFF")

    transcribed = client.post(
        f"/api/projects/{project_id}/transcribe",
        json={"stemId": "source", "engineId": "basic-pitch"},
    )
    assert transcribed.status_code == 200
    assert len(transcribed.json()["notes"]) >= 4
    assert "basic-pitch" in transcribed.json()["message"]

    patched = client.patch(
        f"/api/projects/{project_id}/notes",
        json={
            "notes": [
                {
                    "pitch": 72,
                    "startSec": 0.0,
                    "endSec": 0.75,
                    "velocity": 96,
                    "confidence": 1.0,
                }
            ]
        },
    )
    assert patched.status_code == 200
    assert patched.json()["notes"][0]["pitch"] == 72

    musicxml = client.get(f"/api/projects/{project_id}/export/musicxml")
    assert musicxml.status_code == 200
    assert "attachment;" in musicxml.headers["content-disposition"]
    assert b"<score-partwise" in musicxml.content


def test_api_rejects_unknown_processing_engine(tmp_path):
    client = TestClient(create_app(storage_root=tmp_path))
    created = client.post(
        "/api/projects",
        files={"file": ("demo.wav", make_wav_bytes(), "audio/wav")},
    )
    project_id = created.json()["id"]

    separated = client.post(f"/api/projects/{project_id}/separate", json={"engineId": "missing-engine"})

    assert separated.status_code == 400
    assert "unknown engine" in separated.json()["detail"]
