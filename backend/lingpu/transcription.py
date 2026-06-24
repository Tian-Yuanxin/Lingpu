from __future__ import annotations

import csv
import re
from pathlib import Path

from .models import NoteEvent


def import_transcription_notes(output_root: Path) -> list[NoteEvent]:
    for csv_path in sorted(output_root.rglob("*.csv")):
        notes = _read_note_csv(csv_path)
        if notes:
            return notes

    for midi_path in sorted([*output_root.rglob("*.mid"), *output_root.rglob("*.midi")]):
        notes = read_midi_notes(midi_path.read_bytes())
        if notes:
            return notes

    return []


def _read_note_csv(csv_path: Path) -> list[NoteEvent]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        fields = {_normalized_field(name): name for name in reader.fieldnames}
        start_key = _first_field(fields, ["start_time_s", "start_sec", "start_seconds", "start"])
        end_key = _first_field(fields, ["end_time_s", "end_sec", "end_seconds", "end"])
        pitch_key = _first_field(fields, ["pitch_midi", "midi_pitch", "pitch", "note"])
        velocity_key = _first_field(fields, ["velocity", "amplitude", "confidence"])
        confidence_key = _first_field(fields, ["confidence", "amplitude", "probability"])

        if not start_key or not end_key or not pitch_key:
            return []

        notes = [
            _note_from_values(
                start_sec=_float_value(row.get(start_key)),
                end_sec=_float_value(row.get(end_key)),
                pitch=_int_value(row.get(pitch_key)),
                velocity=_velocity_value(row.get(velocity_key) if velocity_key else None),
                confidence=_confidence_value(row.get(confidence_key) if confidence_key else None),
            )
            for row in reader
        ]
    return sorted([note for note in notes if note is not None], key=lambda note: (note.start_sec, note.pitch, note.end_sec))


def read_midi_notes(content: bytes) -> list[NoteEvent]:
    if len(content) < 14 or content[:4] != b"MThd":
        return []

    header_length = int.from_bytes(content[4:8], "big")
    if header_length < 6 or len(content) < 8 + header_length:
        return []

    track_count = int.from_bytes(content[10:12], "big")
    ticks_per_quarter = int.from_bytes(content[12:14], "big")
    if ticks_per_quarter <= 0 or ticks_per_quarter & 0x8000:
        return []

    offset = 8 + header_length
    notes: list[NoteEvent] = []
    for _index in range(track_count):
        if offset + 8 > len(content) or content[offset : offset + 4] != b"MTrk":
            break
        track_length = int.from_bytes(content[offset + 4 : offset + 8], "big")
        track = content[offset + 8 : offset + 8 + track_length]
        notes.extend(_read_midi_track(track, ticks_per_quarter))
        offset += 8 + track_length

    return sorted(notes, key=lambda note: (note.start_sec, note.pitch, note.end_sec))


def _read_midi_track(track: bytes, ticks_per_quarter: int) -> list[NoteEvent]:
    position = 0
    status: int | None = None
    tempo_us_per_quarter = 500_000
    seconds = 0.0
    active: dict[tuple[int, int], list[tuple[float, int]]] = {}
    notes: list[NoteEvent] = []

    while position < len(track):
        delta, position = _read_variable_length_quantity(track, position)
        seconds += delta * tempo_us_per_quarter / ticks_per_quarter / 1_000_000
        if position >= len(track):
            break

        event_byte = track[position]
        if event_byte & 0x80:
            status = event_byte
            position += 1
        elif status is None:
            break

        if status == 0xFF:
            if position >= len(track):
                break
            meta_type = track[position]
            position += 1
            length, position = _read_variable_length_quantity(track, position)
            payload = track[position : position + length]
            position += length
            if meta_type == 0x51 and len(payload) == 3:
                tempo_us_per_quarter = int.from_bytes(payload, "big")
            continue

        if status in {0xF0, 0xF7}:
            length, position = _read_variable_length_quantity(track, position)
            position += length
            continue

        event_type = status & 0xF0
        channel = status & 0x0F
        data_length = 1 if event_type in {0xC0, 0xD0} else 2
        data = track[position : position + data_length]
        position += data_length
        if len(data) < data_length:
            break

        if event_type == 0x90 and data[1] > 0:
            active.setdefault((channel, data[0]), []).append((seconds, data[1]))
        elif event_type in {0x80, 0x90}:
            started = active.get((channel, data[0]))
            if not started:
                continue
            start_sec, velocity = started.pop(0)
            note = _note_from_values(
                start_sec=start_sec,
                end_sec=seconds,
                pitch=data[0],
                velocity=velocity,
                confidence=0.9,
            )
            if note is not None:
                notes.append(note)

    return notes


def _read_variable_length_quantity(content: bytes, position: int) -> tuple[int, int]:
    value = 0
    for _index in range(4):
        if position >= len(content):
            return value, position
        byte = content[position]
        position += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            break
    return value, position


def _first_field(fields: dict[str, str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        field = fields.get(_normalized_field(candidate))
        if field:
            return field
    return None


def _normalized_field(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _note_from_values(
    start_sec: float | None,
    end_sec: float | None,
    pitch: int | None,
    velocity: int,
    confidence: float,
) -> NoteEvent | None:
    if start_sec is None or end_sec is None or pitch is None:
        return None
    if end_sec <= start_sec:
        return None
    return NoteEvent(
        pitch=max(0, min(127, pitch)),
        start_sec=round(start_sec, 3),
        end_sec=round(end_sec, 3),
        velocity=max(1, min(127, velocity)),
        confidence=max(0.0, min(1.0, confidence)),
    )


def _float_value(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _int_value(value: str | None) -> int | None:
    number = _float_value(value)
    return round(number) if number is not None else None


def _velocity_value(value: str | None) -> int:
    number = _float_value(value)
    if number is None:
        return 90
    if 0 <= number <= 1:
        return round(number * 127)
    return round(number)


def _confidence_value(value: str | None) -> float:
    number = _float_value(value)
    if number is None:
        return 0.9
    if number > 1:
        return number / 127
    return number
