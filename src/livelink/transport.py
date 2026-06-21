"""Transport protocol and built-in implementations.

A Transport abstracts the bidirectional I/O channel between the SDK runtime
and the application's client (browser, mobile app, test harness).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from livelink.streaming import AudioDelta, StreamEvent, StreamInterrupted, TextDelta, TurnComplete

logger = logging.getLogger(__name__)


# --- Input/Output event types ---


@dataclass(frozen=True)
class TextInput:
    """Text message from the client."""

    text: str


@dataclass(frozen=True)
class AudioInput:
    """Audio chunk from the client."""

    data: bytes
    sample_rate: int = 16000


@dataclass(frozen=True)
class ControlInput:
    """Control signal from the client."""

    action: str  # "interrupt", "close", "end_turn"


InputEvent = TextInput | AudioInput | ControlInput


# --- Transport Protocol ---


@runtime_checkable
class Transport(Protocol):
    """Bidirectional I/O channel between SDK and application client.

    Implement this protocol to support custom transport mechanisms.
    The SDK provides built-in implementations for WebSocket and testing.
    """

    async def receive(self) -> AsyncIterator[InputEvent]:
        """Yield input events from the client.

        Must yield events as they arrive. Should handle connection
        close by stopping iteration (not raising).
        """
        ...

    async def send(self, event: StreamEvent) -> None:
        """Send a stream event to the client.

        Implementations should serialize the event appropriately
        for their transport (JSON, binary, etc.).
        """
        ...

    async def close(self) -> None:
        """Close the transport connection."""
        ...


# --- WebSocket Transport ---


class WebSocketTransport:
    """Transport implementation for ASGI-compatible WebSocket connections.

    Works with FastAPI, Starlette, and any ASGI framework.

    Protocol:
    - Text messages: JSON ``{"type": "text", "text": "..."}`` or
      ``{"type": "control", "action": "..."}``
    - Binary messages: Raw PCM16 audio at input_sample_rate

    Output:
    - TextDelta/TurnComplete: JSON text frames
    - AudioDelta: Binary frames (raw PCM bytes)

    Usage::

        from fastapi import FastAPI, WebSocket
        from livelink.transport import WebSocketTransport

        @app.websocket("/ws")
        async def ws(websocket: WebSocket):
            await websocket.accept()
            transport = WebSocketTransport(websocket)
            await agent.session().run(transport)
    """

    def __init__(
        self,
        websocket: Any,
        *,
        input_sample_rate: int = 16000,
        output_sample_rate: int = 24000,
    ) -> None:
        self._ws = websocket
        self._input_sample_rate = input_sample_rate
        self._output_sample_rate = output_sample_rate
        self._closed = False

    async def receive(self) -> AsyncIterator[InputEvent]:
        """Yield input events from the WebSocket client."""
        try:
            while not self._closed:
                message = await self._receive_message()
                if message is None:
                    break

                event = self._parse_input(message)
                if event is not None:
                    yield event
        except Exception as exc:
            logger.debug("WebSocket receive ended: %s", exc)

    async def _receive_message(self) -> dict[str, Any] | bytes | None:
        """Receive a single message from the WebSocket.

        Supports:
        - websockets library (ServerConnection): has recv() returning str|bytes
        - FastAPI/Starlette WebSocket: has receive() returning dict
        """
        try:
            if hasattr(self._ws, "recv"):
                msg = await self._ws.recv()
                if isinstance(msg, bytes):
                    return msg
                elif isinstance(msg, str):
                    return json.loads(msg)
            elif hasattr(self._ws, "receive"):
                msg = await self._ws.receive()
                if isinstance(msg, dict):
                    if msg.get("type") == "websocket.disconnect":
                        return None
                    if "bytes" in msg and msg["bytes"]:
                        return msg["bytes"]
                    if "text" in msg and msg["text"]:
                        return json.loads(msg["text"])
                elif isinstance(msg, bytes):
                    return msg
                elif isinstance(msg, str):
                    return json.loads(msg)
            return None
        except Exception:
            return None

    def _parse_input(self, message: dict[str, Any] | bytes) -> InputEvent | None:
        """Parse a raw message into a typed InputEvent."""
        if isinstance(message, bytes):
            return AudioInput(data=message, sample_rate=self._input_sample_rate)

        if isinstance(message, dict):
            msg_type = message.get("type", "text")
            if msg_type == "text" and "text" in message:
                return TextInput(text=message["text"])
            elif msg_type == "audio" and "data" in message:
                import base64

                audio_bytes = base64.b64decode(message["data"])
                return AudioInput(
                    data=audio_bytes,
                    sample_rate=message.get("sample_rate", self._input_sample_rate),
                )
            elif msg_type == "control":
                return ControlInput(action=message.get("action", ""))

        return None

    async def send(self, event: StreamEvent) -> None:
        """Send a stream event to the WebSocket client."""
        if self._closed:
            return

        try:
            match event:
                case TextDelta(role="user") as td:
                    await self._send_json({"type": "input_transcript", "text": td.text})
                case TextDelta(text=text):
                    await self._send_json({"type": "text", "text": text})
                case AudioDelta(data=data):
                    await self._send_bytes(data)
                case TurnComplete():
                    await self._send_json({"type": "turn_complete"})
                case StreamInterrupted(reason=reason):
                    await self._send_json({"type": "interrupted", "reason": reason})
        except Exception as exc:
            logger.debug("WebSocket send failed: %s", exc)
            self._closed = True

    async def _send_json(self, data: dict[str, Any]) -> None:
        """Send a JSON text frame."""
        text = json.dumps(data)
        if hasattr(self._ws, "send_text"):
            await self._ws.send_text(text)
        elif hasattr(self._ws, "send_json"):
            await self._ws.send_json(data)
        else:
            await self._ws.send(text)

    async def _send_bytes(self, data: bytes) -> None:
        """Send a binary frame."""
        if hasattr(self._ws, "send_bytes"):
            await self._ws.send_bytes(data)
        else:
            await self._ws.send(data)

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if not self._closed:
            self._closed = True
            try:
                await self._ws.close()
            except Exception:
                pass


# --- Test Transport ---


class MemoryTransport:
    """In-memory transport for deterministic testing.

    Usage::

        transport = MemoryTransport()

        # Queue user inputs before running
        transport.queue_text("Hello!")
        transport.queue_audio(b"\\x00" * 3200)

        # Run the session
        session = agent.session()
        await session.run(transport)

        # Inspect outputs
        for event in transport.output_events:
            print(event)
    """

    def __init__(self) -> None:
        self._input_queue: asyncio.Queue[InputEvent | None] = asyncio.Queue()
        self._output_events: list[StreamEvent] = []
        self._closed = False

    def queue_text(self, text: str) -> None:
        """Queue a text input to be received by the session."""
        self._input_queue.put_nowait(TextInput(text=text))

    def queue_audio(self, data: bytes, *, sample_rate: int = 16000) -> None:
        """Queue an audio input to be received by the session."""
        self._input_queue.put_nowait(AudioInput(data=data, sample_rate=sample_rate))

    def queue_control(self, action: str) -> None:
        """Queue a control signal."""
        self._input_queue.put_nowait(ControlInput(action=action))

    def queue_close(self) -> None:
        """Signal end of input."""
        self._input_queue.put_nowait(None)

    async def receive(self) -> AsyncIterator[InputEvent]:
        """Yield queued input events."""
        while not self._closed:
            event = await self._input_queue.get()
            if event is None:
                break
            yield event

    async def send(self, event: StreamEvent) -> None:
        """Collect output events for assertion."""
        self._output_events.append(event)

    async def close(self) -> None:
        self._closed = True

    @property
    def output_events(self) -> list[StreamEvent]:
        """All events sent by the session."""
        return self._output_events

    @property
    def text_output(self) -> str:
        """Concatenated text from all TextDelta events."""
        return "".join(e.text for e in self._output_events if isinstance(e, TextDelta))

    @property
    def audio_output(self) -> bytes:
        """Concatenated audio from all AudioDelta events."""
        return b"".join(e.data for e in self._output_events if isinstance(e, AudioDelta))
