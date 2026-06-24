from __future__ import annotations

import html
import struct
from dataclasses import dataclass

from .models import NoteEvent, Project
from .store import ProjectStore


@dataclass(frozen=True)
class ExportPayload:
    content: bytes
    media_type: str
    filename: str


class ExportService:
    def __init__(self, store: ProjectStore):
        self.store = store

    def export_project(self, project_id: str, file_format: str) -> ExportPayload:
        project = self.store.get_project(project_id)
        normalized = file_format.lower()
        if normalized == "midi":
            return ExportPayload(_write_midi(project), "audio/midi", f"{project.title}.mid")
        if normalized == "musicxml":
            return ExportPayload(
                _write_musicxml(project),
                "application/vnd.recordare.musicxml+xml",
                f"{project.title}.musicxml",
            )
        if normalized == "pdf":
            return ExportPayload(_write_pdf_summary(project), "application/pdf", f"{project.title}.pdf")
        raise ValueError(f"unsupported export format: {file_format}")


def _write_midi(project: Project) -> bytes:
    ticks_per_quarter = 480
    tempo = max(project.score_settings.tempo, 1)
    microseconds_per_quarter = int(60_000_000 / tempo)

    events: list[tuple[int, int, bytes]] = []
    for note in project.notes:
        start_tick = _seconds_to_ticks(note.start_sec, tempo, ticks_per_quarter)
        end_tick = max(start_tick + 1, _seconds_to_ticks(note.end_sec, tempo, ticks_per_quarter))
        velocity = max(1, min(127, note.velocity))
        pitch = max(0, min(127, note.pitch))
        events.append((start_tick, 1, bytes([0x90, pitch, velocity])))
        events.append((end_tick, 0, bytes([0x80, pitch, 0])))

    events.sort(key=lambda item: (item[0], item[1]))

    track = bytearray()
    track.extend(b"\x00\xff\x51\x03")
    track.extend(microseconds_per_quarter.to_bytes(3, "big"))

    last_tick = 0
    for tick, _order, payload in events:
        track.extend(_write_variable_length_quantity(max(0, tick - last_tick)))
        track.extend(payload)
        last_tick = tick
    track.extend(b"\x00\xff\x2f\x00")

    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, ticks_per_quarter)
    return header + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)


def _seconds_to_ticks(seconds: float, tempo: int, ticks_per_quarter: int) -> int:
    return round(seconds * tempo / 60 * ticks_per_quarter)


def _write_variable_length_quantity(value: int) -> bytes:
    chunks = [value & 0x7F]
    value >>= 7
    while value:
        chunks.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(chunks))


def _write_musicxml(project: Project) -> bytes:
    divisions = 4
    tempo = max(project.score_settings.tempo, 1)
    quarter_seconds = 60 / tempo
    notes_xml = "\n".join(_musicxml_note(note, divisions, quarter_seconds) for note in project.notes)
    title = html.escape(project.title)

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <work>
    <work-title>{title}</work-title>
  </work>
  <part-list>
    <score-part id="P1">
      <part-name>Transcription</part-name>
    </score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>{divisions}</divisions>
        <key><fifths>0</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>
      <direction placement="above">
        <direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>{tempo}</per-minute></metronome></direction-type>
        <sound tempo="{tempo}"/>
      </direction>
{notes_xml}
    </measure>
  </part>
</score-partwise>
"""
    return xml.encode("utf-8")


def _musicxml_note(note: NoteEvent, divisions: int, quarter_seconds: float) -> str:
    step, alter, octave = _pitch_to_musicxml(note.pitch)
    duration = max(1, round((note.end_sec - note.start_sec) / quarter_seconds * divisions))
    note_type = _duration_type(duration, divisions)
    alter_xml = f"\n          <alter>{alter}</alter>" if alter else ""
    return f"""      <note>
        <pitch>
          <step>{step}</step>{alter_xml}
          <octave>{octave}</octave>
        </pitch>
        <duration>{duration}</duration>
        <type>{note_type}</type>
      </note>"""


def _pitch_to_musicxml(pitch: int) -> tuple[str, int, int]:
    names = {
        0: ("C", 0),
        1: ("C", 1),
        2: ("D", 0),
        3: ("D", 1),
        4: ("E", 0),
        5: ("F", 0),
        6: ("F", 1),
        7: ("G", 0),
        8: ("G", 1),
        9: ("A", 0),
        10: ("A", 1),
        11: ("B", 0),
    }
    step, alter = names[pitch % 12]
    octave = pitch // 12 - 1
    return step, alter, octave


def _duration_type(duration: int, divisions: int) -> str:
    if duration >= divisions * 4:
        return "whole"
    if duration >= divisions * 2:
        return "half"
    if duration >= divisions:
        return "quarter"
    if duration >= max(1, divisions // 2):
        return "eighth"
    return "16th"


def _write_pdf_summary(project: Project) -> bytes:
    lines = [
        project.title,
        f"Tempo: {project.score_settings.tempo} BPM",
        f"Notes: {len(project.notes)}",
    ]
    lines.extend(
        f"{index + 1}. MIDI {note.pitch}  {note.start_sec:.2f}s-{note.end_sec:.2f}s"
        for index, note in enumerate(project.notes[:18])
    )
    stream = _pdf_text_stream(lines)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")

    xref_start = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Root 1 0 R /Size {len(objects) + 1} >>\nstartxref\n{xref_start}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(output)


def _pdf_text_stream(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 18 Tf", "72 730 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -24 Td")
        commands.append(f"({_escape_pdf_text(line)}) Tj")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1", errors="replace")


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
