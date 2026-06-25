# Lingpu

Lingpu is a local audio-to-score transcription workbench MVP. It runs a
FastAPI backend and serves a static browser UI for uploading audio, creating a
project, previewing stems, editing generated note events, previewing notation,
and exporting MIDI, MusicXML, or PDF.

## Current scope

- Upload an audio file and create a local project under `data/projects/`.
- Run a separation step with the local fallback, Demucs, or audio-separator.
- Run a transcription step with the local placeholder or Basic Pitch.
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
- `basic-pitch`: real audio-to-notes adapter for one prominent separated stem.
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

Python 3.12 works for the core app and separation adapters. Use Python 3.11
when the same environment also needs to run Basic Pitch inference.

Install a Python 3.11 conda environment when Basic Pitch support is needed:

```powershell
conda create -n lingpu311 python=3.11 -y
D:\Anaconda\envs\lingpu311\python.exe -m pip install -e ".[dev,separation,transcription]"
D:\Anaconda\envs\lingpu311\python.exe -m pip install "numpy<2"
```

Basic Pitch currently supports Python 3.7-3.11 upstream. In a Python 3.12
environment the `transcription` extra is skipped by its environment marker, so
the adapter code is available but the Basic Pitch CLI will remain unavailable
until the app is run from a compatible Python environment or upstream publishes
Python 3.12-compatible packages.

Basic Pitch's TensorFlow runtime needs NumPy 1.x, while audio-separator 0.44.x
declares `numpy>=2`. The `lingpu311` deployment above is verified for Basic
Pitch and Demucs, but `pip check` will report that audio-separator metadata
conflict. For strict production isolation, keep audio-separator in a separate
Python 3.12 environment and point `LINGPU_AUDIO_SEPARATOR_BIN` at that CLI.

The local launch script in the `Run locally` section sets the verified
`lingpu311` paths. If you start manually, use explicit model command paths:

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:LINGPU_PYTHON_BIN = "D:\Anaconda\envs\lingpu311\python.exe"
$env:LINGPU_BASIC_PITCH_BIN = "D:\Anaconda\envs\lingpu311\Scripts\basic-pitch.exe"
$env:LINGPU_AUDIO_SEPARATOR_BIN = "D:\Anaconda\envs\lingpu311\Scripts\audio-separator.exe"
D:\Anaconda\envs\lingpu311\python.exe scripts\dev_server.py
```

Install Omnizart separately only when that adapter is being developed:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[omnizart]"
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

Basic Pitch outputs are stored under
`data/projects/<project-id>/transcription/basic-pitch/<stem-id>/`. The adapter
imports note-event CSV first and falls back to MIDI import if no CSV is present.
Basic Pitch works best when the selected stem contains one clear instrument or
voice line.

## Run locally

Use the Windows PowerShell launcher for the verified `lingpu311` conda
environment:

```powershell
.\scripts\dev_server_lingpu311.ps1
```

If the Python executable is installed elsewhere, override only that path:

```powershell
.\scripts\dev_server_lingpu311.ps1 -PythonPath "D:\Anaconda\envs\lingpu311\python.exe"
```

The script prepends the conda environment, `Scripts`, `Library\bin`, and
`Library\usr\bin` directories to `PATH`, sets `PYTHONIOENCODING`,
`LINGPU_PYTHON_BIN`, `LINGPU_BASIC_PITCH_BIN`, and
`LINGPU_AUDIO_SEPARATOR_BIN`, starts the server from the repository root, and
prints `http://127.0.0.1:8000`.

Manual equivalent:

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:LINGPU_PYTHON_BIN = "D:\Anaconda\envs\lingpu311\python.exe"
$env:LINGPU_BASIC_PITCH_BIN = "D:\Anaconda\envs\lingpu311\Scripts\basic-pitch.exe"
$env:LINGPU_AUDIO_SEPARATOR_BIN = "D:\Anaconda\envs\lingpu311\Scripts\audio-separator.exe"
D:\Anaconda\envs\lingpu311\python.exe scripts\dev_server.py
```

Open `http://127.0.0.1:8000`.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The pytest configuration uses `.pytest-tmp/` as its temp directory so tests work
inside the managed workspace sandbox.
