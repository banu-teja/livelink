from __future__ import annotations

from relaykit.adapters.base import BaseAdapter
from relaykit.capabilities import Capability
from relaykit.registry import ModelInfo, register_model

# Lazy registration: only register adapters whose provider SDK is installed.
# Users install the SDK they need via: pip install relaykit[gemini] or relaykit[openai]

try:
    from relaykit.adapters.gemini import GeminiLiveAdapter

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
    from relaykit.adapters.openai import OpenAIRealtimeAdapter

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
