from __future__ import annotations

from livelink.adapters.base import BaseAdapter
from livelink.capabilities import Capability
from livelink.registry import ModelInfo, register_model

# Lazy registration: only register adapters whose provider SDK is installed.
# Users install the SDK they need via: pip install livelink[gemini] or livelink[openai]

try:
    from livelink.adapters.gemini import GeminiLiveAdapter

    register_model(
        "gemini-2.5-flash-native-audio",
        ModelInfo(
            adapter_class=GeminiLiveAdapter,
            capabilities=frozenset(
                {Capability.AUDIO_IN, Capability.AUDIO_OUT, Capability.TEXT_IN, Capability.TEXT_OUT}
            ),
            transport="websocket",
            default_config={"model": "gemini-live-2.5-flash-native-audio"},
            provider="gemini",
        ),
    )

    register_model(
        "gemini-2.0-flash-live",
        ModelInfo(
            adapter_class=GeminiLiveAdapter,
            capabilities=frozenset(
                {Capability.AUDIO_IN, Capability.AUDIO_OUT, Capability.TEXT_IN, Capability.TEXT_OUT}
            ),
            transport="websocket",
            default_config={"model": "gemini-2.0-flash-live-001"},
            provider="gemini",
        ),
    )
except ImportError:
    pass

try:
    from livelink.adapters.openai import OpenAIRealtimeAdapter

    register_model(
        "gpt-4o-realtime",
        ModelInfo(
            adapter_class=OpenAIRealtimeAdapter,
            capabilities=frozenset(
                {Capability.AUDIO_IN, Capability.AUDIO_OUT, Capability.TEXT_IN, Capability.TEXT_OUT}
            ),
            transport="websocket",
            default_config={"model": "gpt-4o-realtime-preview"},
            provider="openai",
        ),
    )

    register_model(
        "gpt-4o-mini-realtime",
        ModelInfo(
            adapter_class=OpenAIRealtimeAdapter,
            capabilities=frozenset(
                {Capability.AUDIO_IN, Capability.AUDIO_OUT, Capability.TEXT_IN, Capability.TEXT_OUT}
            ),
            transport="websocket",
            default_config={"model": "gpt-4o-mini-realtime-preview"},
            provider="openai",
        ),
    )
except ImportError:
    pass

__all__ = ["BaseAdapter"]
