import io
import math
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from lingpu.exporters import ExportService
from lingpu.models import NoteEvent
from lingpu.processing import EngineRegistry, ProcessingService
from lingpu.store import ProjectStore


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


def test_project_pipeline_uses_local_fallback_when_models_are_unavailable(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create_project("demo.wav", make_wav_bytes())

    assert project.status == "uploaded"
    assert project.source_audio.name == "source.wav"
    assert store.source_audio_path(project.id).exists()

    processing = ProcessingService(store)
    separated = processing.separate(project.id)

    assert separated.status == "separated"
    assert [stem.id for stem in separated.stems] == ["source"]
    assert separated.stems[0].label == "Original mix"
    assert separated.stems[0].engine == "local-fallback"

    transcribed = processing.transcribe(project.id, stem_id="source")

    assert transcribed.status == "transcribed"
    assert transcribed.score_settings.tempo == 120
    assert len(transcribed.notes) >= 4
    assert transcribed.notes[0].pitch == 60
    assert transcribed.notes[0].start_sec == 0
    assert transcribed.notes[0].end_sec > transcribed.notes[0].start_sec


def test_engine_registry_exposes_separation_and_transcription_options():
    registry = EngineRegistry(
        detectors={
            "local-fallback": True,
            "demucs": False,
            "uvr": False,
            "audio-separator": False,
            "basic-pitch": False,
            "omnizart": False,
            "mt3": False,
        }
    )

    engines = registry.list_engines()
    by_id = {engine.id: engine for engine in engines}

    assert by_id["local-fallback"].kind == "separation"
    assert by_id["local-fallback"].available is True
    assert by_id["demucs"].kind == "separation"
    assert by_id["demucs"].available is False
    assert by_id["basic-pitch"].kind == "transcription"
    assert by_id["basic-pitch"].available is False


def test_requested_unavailable_engines_are_recorded_with_fallback_message(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create_project("demo.wav", make_wav_bytes())
    processing = ProcessingService(
        store,
        registry=EngineRegistry(
            detectors={
                "local-fallback": True,
                "demucs": False,
                "uvr": False,
                "audio-separator": False,
                "basic-pitch": False,
                "omnizart": False,
                "mt3": False,
            }
        ),
    )

    separated = processing.separate(project.id, engine_id="demucs")
    transcribed = processing.transcribe(project.id, stem_id="source", engine_id="basic-pitch")

    assert separated.stems[0].engine == "demucs"
    assert "not available" in separated.message
    assert transcribed.message is not None
    assert "basic-pitch" in transcribed.message
    assert "fallback" in transcribed.message


def test_demucs_adapter_imports_generated_stems(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create_project("demo.wav", make_wav_bytes())

    def fake_runner(command, cwd, timeout_seconds):
        output_root = Path(command[command.index("-o") + 1])
        track_dir = output_root / "htdemucs" / "source"
        track_dir.mkdir(parents=True)
        for name in ["vocals", "drums", "bass", "other"]:
            (track_dir / f"{name}.wav").write_bytes(make_wav_bytes(0.1))
        return 0, "ok", ""

    processing = ProcessingService(
        store,
        registry=EngineRegistry(detectors={"demucs": True}),
        command_runner=fake_runner,
    )

    separated = processing.separate(project.id, engine_id="demucs")

    assert separated.status == "separated"
    assert separated.message == "Demucs separated 4 stems."
    assert {stem.id for stem in separated.stems} == {"vocals", "drums", "bass", "other"}
    assert all(stem.engine == "demucs" for stem in separated.stems)
    assert all(store.project_file_path(project.id, stem.audio.path).exists() for stem in separated.stems)


def test_audio_separator_adapter_imports_generated_stems(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create_project("demo.wav", make_wav_bytes())

    def fake_runner(command, cwd, timeout_seconds):
        output_root = Path(command[command.index("--output_dir") + 1])
        output_root.mkdir(parents=True)
        (output_root / "source_(Vocals)_model.wav").write_bytes(make_wav_bytes(0.1))
        (output_root / "source_(Instrumental)_model.wav").write_bytes(make_wav_bytes(0.1))
        return 0, "ok", ""

    processing = ProcessingService(
        store,
        registry=EngineRegistry(detectors={"audio-separator": True}),
        command_runner=fake_runner,
    )

    separated = processing.separate(project.id, engine_id="audio-separator")

    assert separated.status == "separated"
    assert separated.message == "audio-separator separated 2 stems."
    assert {stem.id for stem in separated.stems} == {"vocals", "instrumental"}
    assert all(stem.engine == "audio-separator" for stem in separated.stems)


def test_basic_pitch_adapter_imports_note_event_csv(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create_project("demo.wav", make_wav_bytes())
    processing = ProcessingService(store)
    separated = processing.separate(project.id)

    def fake_runner(command, cwd, timeout_seconds):
        output_root = Path(command[1])
        assert output_root.is_dir()
        (output_root / "source_basic_pitch.csv").write_text(
            "start_time_s,end_time_s,pitch_midi,velocity,confidence\n"
            "0.125,0.500,64,92,0.91\n"
            "0.500,0.875,67,88,0.84\n",
            encoding="utf-8",
        )
        return 0, "ok", ""

    processing = ProcessingService(
        store,
        registry=EngineRegistry(detectors={"basic-pitch": True}),
        command_runner=fake_runner,
    )

    transcribed = processing.transcribe(separated.id, stem_id="source", engine_id="basic-pitch")

    assert transcribed.status == "transcribed"
    assert transcribed.message == "Basic Pitch imported 2 notes."
    assert [(note.pitch, note.start_sec, note.end_sec) for note in transcribed.notes] == [
        (64, 0.125, 0.5),
        (67, 0.5, 0.875),
    ]
    assert transcribed.notes[0].velocity == 92
    assert transcribed.notes[0].confidence == 0.91


def test_basic_pitch_adapter_imports_midi_when_csv_is_missing(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create_project("demo.wav", make_wav_bytes())
    processing = ProcessingService(store)
    separated = processing.separate(project.id)

    midi_project = store.replace_notes(
        project.id,
        [
            NoteEvent(pitch=60, start_sec=0.0, end_sec=0.5, velocity=90, confidence=0.9),
            NoteEvent(pitch=72, start_sec=0.5, end_sec=1.0, velocity=80, confidence=0.9),
        ],
    )
    midi_bytes = ExportService(store).export_project(midi_project.id, "midi").content

    def fake_runner(command, cwd, timeout_seconds):
        output_root = Path(command[1])
        assert output_root.is_dir()
        (output_root / "source_basic_pitch.mid").write_bytes(midi_bytes)
        return 0, "ok", ""

    processing = ProcessingService(
        store,
        registry=EngineRegistry(detectors={"basic-pitch": True}),
        command_runner=fake_runner,
    )

    transcribed = processing.transcribe(separated.id, stem_id="source", engine_id="basic-pitch")

    assert transcribed.message == "Basic Pitch imported 2 notes."
    assert [note.pitch for note in transcribed.notes] == [60, 72]
    assert [note.velocity for note in transcribed.notes] == [90, 80]
    assert transcribed.notes[1].start_sec == 0.5


def test_basic_pitch_adapter_imports_csv_with_pitch_bend_values(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create_project("demo.wav", make_wav_bytes())
    processing = ProcessingService(store)
    separated = processing.separate(project.id)

    def fake_runner(command, cwd, timeout_seconds):
        output_root = Path(command[1])
        assert output_root.is_dir()
        (output_root / "source_basic_pitch.csv").write_text(
            "start_time_s,end_time_s,pitch_midi,velocity,pitch_bend\n"
            "0.023,0.987,69,83,1,1,1,1\n",
            encoding="utf-8",
        )
        return 0, "ok", ""

    processing = ProcessingService(
        store,
        registry=EngineRegistry(detectors={"basic-pitch": True}),
        command_runner=fake_runner,
    )

    transcribed = processing.transcribe(separated.id, stem_id="source", engine_id="basic-pitch")

    assert transcribed.message == "Basic Pitch imported 1 notes."
    assert transcribed.notes[0].pitch == 69
    assert transcribed.notes[0].velocity == 83
    assert transcribed.notes[0].confidence == 0.9


def test_basic_pitch_adapter_falls_back_when_command_fails(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create_project("demo.wav", make_wav_bytes())
    processing = ProcessingService(store)
    separated = processing.separate(project.id)

    def fake_runner(command, cwd, timeout_seconds):
        return 2, "", "model error"

    processing = ProcessingService(
        store,
        registry=EngineRegistry(detectors={"basic-pitch": True}),
        command_runner=fake_runner,
    )

    transcribed = processing.transcribe(separated.id, stem_id="source", engine_id="basic-pitch")

    assert transcribed.status == "transcribed"
    assert transcribed.notes[0].pitch == 60
    assert transcribed.message is not None
    assert "Basic Pitch failed with exit code 2" in transcribed.message
    assert "fallback" in transcribed.message


def test_note_replacement_is_sorted_and_persisted(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create_project("demo.wav", make_wav_bytes())

    notes = [
        NoteEvent(pitch=67, start_sec=1.0, end_sec=1.5, velocity=82, confidence=0.7),
        NoteEvent(pitch=64, start_sec=0.0, end_sec=0.5, velocity=88, confidence=0.9),
    ]

    updated = store.replace_notes(project.id, notes)
    reloaded = store.get_project(project.id)

    assert [note.pitch for note in updated.notes] == [64, 67]
    assert [note.pitch for note in reloaded.notes] == [64, 67]


def test_exports_generate_midi_musicxml_and_pdf_payloads(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create_project("demo.wav", make_wav_bytes())
    store.replace_notes(
        project.id,
        [
            NoteEvent(pitch=60, start_sec=0.0, end_sec=0.5, velocity=90, confidence=0.9),
            NoteEvent(pitch=64, start_sec=0.5, end_sec=1.0, velocity=90, confidence=0.9),
        ],
    )

    exports = ExportService(store)

    midi = exports.export_project(project.id, "midi")
    musicxml = exports.export_project(project.id, "musicxml")
    pdf = exports.export_project(project.id, "pdf")

    assert midi.media_type == "audio/midi"
    assert midi.filename.endswith(".mid")
    assert midi.content.startswith(b"MThd")

    assert musicxml.media_type == "application/vnd.recordare.musicxml+xml"
    assert b"<score-partwise" in musicxml.content
    assert b"<step>C</step>" in musicxml.content

    assert pdf.media_type == "application/pdf"
    assert pdf.filename.endswith(".pdf")
    assert pdf.content.startswith(b"%PDF-")
