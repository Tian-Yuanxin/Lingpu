from __future__ import annotations

import sys
from pathlib import Path

import soundfile as sf
import torch


def main(argv: list[str] | None = None) -> int | None:
    _add_static_ffmpeg_to_path()

    import demucs.audio as demucs_audio
    import demucs.separate as demucs_separate

    demucs_audio.save_audio = _save_audio
    demucs_separate.save_audio = _save_audio
    return demucs_separate.main(argv)


def _save_audio(
    wav: torch.Tensor,
    path: str | Path,
    samplerate: int,
    bitrate: int = 320,
    clip: str = "rescale",
    bits_per_sample: int = 16,
    as_float: bool = False,
    preset: int = 2,
) -> None:
    import demucs.audio as demucs_audio

    wav = demucs_audio.prevent_clip(wav, mode=clip)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.suffix.lower() == ".mp3":
        demucs_audio.encode_mp3(wav, path, samplerate, bitrate, preset, verbose=True)
        return

    data = wav.detach().cpu()
    if data.dim() == 1:
        data = data.unsqueeze(0)
    data = data.transpose(0, 1).numpy()
    sf.write(str(path), data, samplerate, subtype=_soundfile_subtype(path, bits_per_sample, as_float))


def _soundfile_subtype(path: Path, bits_per_sample: int, as_float: bool) -> str:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        if as_float:
            return "FLOAT"
        if bits_per_sample == 24:
            return "PCM_24"
        if bits_per_sample == 32:
            return "PCM_32"
        return "PCM_16"
    if suffix == ".flac":
        return "PCM_24" if bits_per_sample == 24 else "PCM_16"
    raise ValueError(f"Invalid suffix for path: {suffix}")


def _add_static_ffmpeg_to_path() -> None:
    try:
        import static_ffmpeg
    except ImportError:
        return
    static_ffmpeg.add_paths(weak=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
