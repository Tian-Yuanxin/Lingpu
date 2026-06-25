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
        json={"stemId": "source", "engineId": "local-placeholder"},
    )
    assert transcribed.status_code == 200
    assert len(transcribed.json()["notes"]) >= 4
    assert "placeholder" in transcribed.json()["message"]

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


def test_api_lists_projects_and_patches_score_settings_with_aliases(tmp_path):
    client = TestClient(create_app(storage_root=tmp_path))
    first = client.post(
        "/api/projects",
        files={"file": ("first.wav", make_wav_bytes(), "audio/wav")},
    ).json()
    second = client.post(
        "/api/projects",
        files={"file": ("second.wav", make_wav_bytes(), "audio/wav")},
    ).json()

    patched = client.patch(
        f"/api/projects/{first['id']}/score-settings",
        json={
            "tempo": 96,
            "timeSignature": "3/4",
            "keySignature": "G",
            "quantization": "1/8",
        },
    )
    assert patched.status_code == 200
    patched_body = patched.json()
    assert patched_body["scoreSettings"]["timeSignature"] == "3/4"
    assert patched_body["scoreSettings"]["keySignature"] == "G"
    assert "score_settings" not in patched_body
    assert "time_signature" not in patched_body["scoreSettings"]

    reloaded = client.get(f"/api/projects/{first['id']}")
    assert reloaded.status_code == 200
    assert reloaded.json()["scoreSettings"]["tempo"] == 96

    listed = client.get("/api/projects")
    assert listed.status_code == 200
    listed_body = listed.json()
    assert [project["id"] for project in listed_body] == [first["id"], second["id"]]
    assert "updatedAt" in listed_body[0]
    assert "updated_at" not in listed_body[0]


def test_api_score_settings_patch_returns_404_for_missing_project(tmp_path):
    client = TestClient(create_app(storage_root=tmp_path))

    response = client.patch(
        "/api/projects/000000000000/score-settings",
        json={"tempo": 96, "timeSignature": "3/4", "keySignature": "G", "quantization": "1/8"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "project not found"


def test_api_rejects_invalid_score_settings(tmp_path):
    client = TestClient(create_app(storage_root=tmp_path))
    created = client.post(
        "/api/projects",
        files={"file": ("demo.wav", make_wav_bytes(), "audio/wav")},
    )
    project_id = created.json()["id"]

    response = client.patch(
        f"/api/projects/{project_id}/score-settings",
        json={"tempo": 0, "timeSignature": "3/4", "keySignature": "G", "quantization": "1/7"},
    )

    assert response.status_code == 422
