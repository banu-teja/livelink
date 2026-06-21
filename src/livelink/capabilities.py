from __future__ import annotations

from enum import Enum


class Capability(str, Enum):
    """Model capabilities for modality and feature support.

    Inherits from str to maintain backward compatibility with existing
    frozenset[str] checks (e.g., "audio_in" in model.capabilities).
    """

    AUDIO_IN = "audio_in"
    AUDIO_OUT = "audio_out"
    TEXT_IN = "text_in"
    TEXT_OUT = "text_out"
    TOOL_USE = "tool_use"
    VIDEO_IN = "video_in"
