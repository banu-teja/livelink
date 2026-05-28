"""BaseAdapter: abstract interface for realtime model providers.

RealtimeSession interacts with adapters exclusively through this interface.
Provider SDKs are wrapped behind these methods — application code never
touches adapter internals directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from relaykit.types import ConversationTurn, LiveChunk, ToolResponse


class BaseAdapter(ABC):
    """Abstract base for provider adapters.

    Lifecycle: construct → connect(config) → send/stream/receive → disconnect

    Subclasses implement the abstract methods to bridge a specific provider
    SDK (Gemini, OpenAI, etc.) to the unified LiveChunk protocol.
    """

    @abstractmethod
    async def connect(self, config: dict[str, Any]) -> None:
        """Connect to the provider with the given configuration.

        Config keys (all optional, adapter picks what it uses):
            - system_instruction: str
            - voice: str
            - tools: list[dict] (JSON Schema tool declarations)
            - model: str (provider-specific model identifier)
            - Plus any provider_options from AgentConfig
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the provider and release resources."""
        ...

    @abstractmethod
    async def send(self, content: str | bytes, *, mime_type: str = "audio/pcm") -> None:
        """Send input (text or audio) to the model.

        For streaming/realtime providers, this pushes data into the active session.
        For request/response providers, this may buffer until the next receive call.
        """
        ...

    @abstractmethod
    def receive(self) -> AsyncIterator[LiveChunk]:
        """Yield output chunks from the model.

        This is the primary output method. Yields LiveChunk events as the model
        generates them (text deltas, audio deltas, tool calls, turn_end, etc.).

        For duplex providers, this runs concurrently with send() calls.
        """
        ...

    async def cancel_response(self) -> None:
        """Cancel the model's current generation (interruption).

        Default is a no-op. Override for providers that support mid-generation cancellation.
        """

    async def end_audio_stream(self) -> None:
        """Signal that the audio input stream has ended (explicit turn boundary).

        Default is a no-op. Override for providers that distinguish between
        VAD-detected turn ends and explicit stream termination.
        """

    async def send_tool_response(self, responses: list[ToolResponse]) -> None:
        """Send tool execution results back to the model.

        After the session executes tool calls, it sends results here so the model
        can continue generating with the tool outputs.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support tool/function calling")

    async def restore_history(self, turns: list[ConversationTurn]) -> None:
        """Restore conversation history (for session resumption).

        Default is a no-op. Override for providers that accept history injection.
        """

    async def heartbeat_loop(self) -> None:
        """Optional keep-alive loop run as a background task by RealtimeSession.

        Default is a no-op (returns immediately). Override in adapters that require
        periodic signals to maintain connections (e.g. Gemini needs silence packets).
        """

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the adapter currently has an active provider connection."""
        ...
