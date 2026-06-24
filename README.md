# Lingpu

Lingpu is a local audio-to-score transcription workbench MVP. It runs a
FastAPI backend and serves a static browser UI for uploading audio, creating a
project, previewing stems, editing generated note events, previewing notation,
and exporting MIDI, MusicXML, or PDF.

## Current scope

- Upload an audio file and create a local project under `data/projects/`.
- Run a separation step with the local fallback, Demucs, or audio-separator.
- Run a transcription step. In the offline MVP this creates deterministic
  placeholder notes so the editing, preview, and export workflow can be used.
- Edit note pitch, start time, and end time in the browser.
- Export generated notes as `.mid`, `.musicxml`, or `.pdf`.

Demucs and audio-separator are optional model dependencies because they install
large PyTorch/ONNX runtimes and download model weights into local caches.

## Processing engines

The app exposes engine metadata through `GET /api/engines` and lets the UI send
an `engineId` when running separation or transcription.

Separation targets:

- `local-fallback`: always available; uses the original mix as one editable stem.
- `demucs`: vocals/drums/bass/other stem separation through the local
  `lingpu.demucs_runner` compatibility wrapper.
- `uvr`: available when the audio-separator CLI is installed.
- `audio-separator`: UVR/MDX-style vocal/instrumental separation through the
  audio-separator CLI.

Transcription targets:

- `local-placeholder`: always available; creates deterministic editable notes.
- `basic-pitch`: first real transcription adapter target for single stems.
- `omnizart`: later adapter target for melody/vocal/drum/chord tasks.
- `mt3`: later research adapter target for multi-instrument transcription.

Unavailable engines stay visible in the API so the UI can explain what is
missing. If a model command fails, the project records the requested engine and
falls back to the original mix so editing/export can still continue.

## Model deployment

Create the local environment and install the runtime:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e ".[dev,separation]"
```

The Windows deployment uses `static-ffmpeg` for `ffmpeg`/`ffprobe`, and the
Demucs adapter writes WAV/FLAC files through `soundfile` to avoid torchaudio's
TorchCodec shared-library path on Windows.

Preload the default audio-separator model:

```powershell
.\.venv\Scripts\audio-separator.exe --download_model_only `
  --model_filename model_bs_roformer_ep_317_sdr_12.9755.ckpt `
  --model_file_dir data\models\audio-separator
```

Demucs downloads its model weights on first run. audio-separator model weights
are cached under `data/models/audio-separator/`; generated project stems are
stored under each project directory in `data/projects/`.

## Run locally

```powershell
.\.venv\Scripts\python.exe scripts\dev_server.py
```

Open `http://127.0.0.1:8000`.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The pytest configuration uses `.pytest-tmp/` as its temp directory so tests work
inside the managed workspace sandbox.
