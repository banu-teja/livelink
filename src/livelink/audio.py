from __future__ import annotations

import asyncio
import functools
from pathlib import Path

import numpy as np


def decode_audio_file(path: Path) -> bytes:
    """
    Decode an audio file to raw PCM16 bytes.
    Supports .wav and .mp3 (requires pydub for .mp3).
    Returns raw PCM16 bytes (not normalized yet — call normalize_pcm16 next).
    """
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return _decode_wav(path)
    if suffix == ".mp3":
        return _decode_mp3(path)
    raise UnsupportedFormatError(f"Unsupported audio format: {suffix}. Supported: .wav, .mp3")


def normalize_pcm16(pcm: bytes, src_rate: int = 16000, target_rate: int = 16000) -> bytes:
    """
    Normalize raw PCM16 bytes to PCM16, target_rate Hz, mono.
    If src_rate != target_rate, resamples using linear interpolation.
    """
    samples = np.frombuffer(pcm, dtype=np.int16)
    if len(samples.shape) > 1:
        samples = samples.mean(axis=1).astype(np.int16)  # stereo → mono
    if src_rate != target_rate:
        samples = _resample(samples, src_rate, target_rate)
    return samples.tobytes()


async def decode_audio_file_async(path: Path) -> bytes:
    """Async version of decode_audio_file — runs in thread pool executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, decode_audio_file, path)


async def normalize_pcm16_async(
    pcm: bytes, src_rate: int = 16000, target_rate: int = 16000
) -> bytes:
    """Async version of normalize_pcm16 — runs in thread pool executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, functools.partial(normalize_pcm16, pcm, src_rate=src_rate, target_rate=target_rate)
    )


def _decode_wav(path: Path) -> bytes:
    try:
        import soundfile as sf
    except ImportError:
        raise ImportError("soundfile is required for .wav decoding: pip install soundfile")
    data, sample_rate = sf.read(str(path), dtype="int16", always_2d=False)
    return data.tobytes()


def _decode_mp3(path: Path) -> bytes:
    try:
        from pydub import AudioSegment
    except ImportError:
        raise ImportError("pydub is required for .mp3 decoding: pip install livelink[pydub]")
    audio = AudioSegment.from_mp3(str(path))
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    return audio.raw_data


def _resample(samples: np.ndarray, src_rate: int, target_rate: int) -> np.ndarray:
    ratio = target_rate / src_rate
    new_length = int(len(samples) * ratio)
    indices = np.linspace(0, len(samples) - 1, new_length)
    return np.interp(indices, np.arange(len(samples)), samples).astype(np.int16)


from livelink.exceptions import UnsupportedFormatError  # noqa: E402
