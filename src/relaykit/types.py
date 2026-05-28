from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class Usage:
    """Token and duration usage tracking for a single response."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    audio_duration_ms: int | None = None


@dataclass(frozen=True)
class LiveResponse:
    text: str | None = None
    audio: bytes | None = None
    duration_ms: int = 0
    usage: Usage | None = None
    model: str | None = None
    provider: str | None = None

    def save_wav(
        self,
        path: str | Path,
        *,
        sample_rate: int = 24000,
        channels: int = 1,
        sample_width: int = 2,
    ) -> Path:
        """Save the audio response as a WAV file.

        Args:
            path: Destination file path (.wav extension recommended).
            sample_rate: Audio sample rate in Hz. Defaults to 24000 (standard
                for Gemini Live and OpenAI Realtime output).
            channels: Number of audio channels. Defaults to 1 (mono).
            sample_width: Bytes per sample. Defaults to 2 (16-bit PCM).

        Returns:
            The resolved Path to the written file.

        Raises:
            ValueError: If no audio data is present on this response.
        """
        if self.audio is None:
            raise ValueError(
                "No audio data in this response. "
                "Ensure the model supports audio output and output_modalities includes 'AUDIO'."
            )
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(dest), "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(self.audio)
        return dest


@dataclass(frozen=True)
class LiveChunk:
    type: Literal[
        "text",
        "audio",
        "turn_end",
        "interrupted",
        "transcript",
        "input_transcript",
        "session_reconnecting",
        "tool_call",
        "tool_call_cancellation",
    ]
    text: str | None = None
    audio: bytes | None = None
    tool_calls: tuple[ToolCallData, ...] | None = None
    tool_call_ids: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ConversationTurn:
    role: Literal["user", "model"]
    text: str | None = None
    audio: bytes | None = None
    timestamp: float = 0.0


@dataclass(frozen=True)
class ToolCallData:
    """A single tool/function call from the model."""

    id: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ToolResponse:
    """Result of executing a tool call, sent back to the model."""

    call_id: str
    result: str
