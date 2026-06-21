"""Streaming primitives: typed StreamEvent union and AudioFrame."""

from __future__ import annotations

from dataclasses import dataclass

from livelink.types import LiveResponse


# --- Stream Events (typed union) ---


@dataclass(frozen=True)
class TextDelta:
    """A chunk of text from the model."""

    text: str
    role: str = "assistant"


@dataclass(frozen=True)
class AudioDelta:
    """A chunk of audio from the model."""

    data: bytes
    sample_rate: int = 24000
    channels: int = 1
    sample_width: int = 2

    @property
    def duration_ms(self) -> float:
        bytes_per_sample = self.sample_width * self.channels
        if bytes_per_sample == 0:
            return 0.0
        num_samples = len(self.data) / bytes_per_sample
        return (num_samples / self.sample_rate) * 1000


@dataclass(frozen=True)
class TurnComplete:
    """Signals end of a model turn with the accumulated response."""

    response: LiveResponse


@dataclass(frozen=True)
class StreamInterrupted:
    """Session is reconnecting mid-stream."""

    reason: str = "session_reconnecting"


StreamEvent = TextDelta | AudioDelta | TurnComplete | StreamInterrupted


# --- AudioFrame ---


@dataclass(frozen=True)
class AudioFrame:
    """A typed audio frame with metadata for processing pipelines."""

    data: bytes
    sample_rate: int = 24000
    channels: int = 1
    sample_width: int = 2
    timestamp_ms: float = 0.0

    @property
    def duration_ms(self) -> float:
        bytes_per_sample = self.sample_width * self.channels
        if bytes_per_sample == 0:
            return 0.0
        num_samples = len(self.data) / bytes_per_sample
        return (num_samples / self.sample_rate) * 1000

    @property
    def num_samples(self) -> int:
        bytes_per_sample = self.sample_width * self.channels
        if bytes_per_sample == 0:
            return 0
        return len(self.data) // bytes_per_sample
