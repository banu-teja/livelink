from __future__ import annotations

import base64
import logging
from typing import Any, AsyncIterator

try:
    import openai as _openai_module  # noqa: F401
except ImportError as _import_err:
    raise ImportError(
        "The openai package is required for the OpenAI Realtime adapter. "
        "Install it with: pip install livelink[openai]"
    ) from _import_err

from livelink.adapters.base import BaseAdapter
from livelink.exceptions import AdapterError, AuthenticationError
from livelink.types import ConversationTurn, LiveChunk, ToolCallData, ToolResponse

logger = logging.getLogger(__name__)


class OpenAIRealtimeAdapter(BaseAdapter):
    """OpenAI Realtime API adapter using the async SDK websocket connection.

    Lifecycle: construct (no args) → connect(config) → send/receive → disconnect
    """

    def __init__(self) -> None:
        self._client: Any = None
        self._connection: Any = None
        self._connected: bool = False
        self._max_history_turns: int = 20

    async def connect(self, config: dict[str, Any]) -> None:
        from openai import AsyncOpenAI, OpenAIError

        model = config.get("model", "gpt-realtime-2")
        api_key = config.get("api_key")
        system_instruction = config.get("system_instruction")
        voice = config.get("voice")
        output_modalities = config.get("output_modalities", ["text"])
        self._max_history_turns = config.get("max_history_turns", 20)
        tools = config.get("tools")

        try:
            self._client = AsyncOpenAI(api_key=api_key)
        except OpenAIError as exc:
            raise AuthenticationError(str(exc)) from exc

        try:
            self._connection = await self._client.realtime.connect(
                model=model,
            ).enter()
        except Exception as exc:
            raise AdapterError(f"Failed to open realtime connection: {exc}") from exc

        session_config: dict[str, Any] = {}
        if system_instruction is not None:
            session_config["instructions"] = system_instruction
        session_config["output_modalities"] = output_modalities
        if voice is not None:
            session_config["voice"] = voice
        if tools is not None:
            session_config["tools"] = [
                {
                    "type": "function",
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {}),
                }
                for tool in tools
            ]

        try:
            await self._connection.session.update(session=session_config)
        except Exception as exc:
            raise AdapterError(f"Failed to configure session: {exc}") from exc

        try:
            async for event in self._connection:
                if event.type == "session.updated":
                    break
        except Exception as exc:
            raise AdapterError(f"Error waiting for session confirmation: {exc}") from exc

        self._connected = True
        logger.info("OpenAI Realtime connection established (model=%s)", model)

    async def disconnect(self) -> None:
        self._connected = False
        if self._connection is not None:
            try:
                await self._connection.close()
            except Exception as exc:
                logger.warning("Error closing connection: %s", exc)
            finally:
                self._connection = None

    async def send(self, content: str | bytes, *, mime_type: str = "audio/pcm") -> None:
        if not self._connected or self._connection is None:
            raise AdapterError("Not connected")

        try:
            if isinstance(content, bytes):
                b64 = base64.b64encode(content).decode("ascii")
                await self._connection.input_audio_buffer.append(audio=b64)
                await self._connection.input_audio_buffer.commit()
            else:
                await self._connection.conversation.item.create(
                    item={
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": content}],
                    }
                )

            await self._connection.response.create()
        except AdapterError:
            raise
        except Exception as exc:
            raise AdapterError(f"Error during send: {exc}") from exc

    async def receive(self) -> AsyncIterator[LiveChunk]:
        if not self._connected or self._connection is None:
            raise AdapterError("Not connected")

        try:
            async for event in self._connection:
                match event.type:
                    case "response.text.delta":
                        yield LiveChunk(type="text", text=event.delta)

                    case "response.audio.delta":
                        yield LiveChunk(
                            type="audio",
                            audio=base64.b64decode(event.delta),
                        )

                    case "response.function_call_arguments.done":
                        tool_call = ToolCallData(
                            id=event.call_id,
                            name=event.name,
                            args=_parse_json_args(event.arguments),
                        )
                        yield LiveChunk(
                            type="tool_call",
                            tool_calls=(tool_call,),
                        )

                    case "response.done":
                        yield LiveChunk(type="turn_end")

                    case "error":
                        raise AdapterError(
                            getattr(event, "error", None)
                            and getattr(event.error, "message", str(event))
                            or str(event)
                        )
        except AdapterError:
            raise
        except Exception as exc:
            if not self._connected:
                return
            raise AdapterError(f"Error in receive loop: {exc}") from exc

    async def cancel_response(self) -> None:
        if self._connection is not None:
            try:
                await self._connection.response.cancel()
            except Exception as exc:
                logger.warning("Error cancelling response: %s", exc)

    async def send_tool_response(self, responses: list[ToolResponse]) -> None:
        if not self._connected or self._connection is None:
            raise AdapterError("Not connected")

        try:
            for response in responses:
                await self._connection.conversation.item.create(
                    item={
                        "type": "function_call_output",
                        "call_id": response.call_id,
                        "output": response.result,
                    }
                )
            await self._connection.response.create()
        except AdapterError:
            raise
        except Exception as exc:
            raise AdapterError(f"Error sending tool response: {exc}") from exc

    async def restore_history(self, turns: list[ConversationTurn]) -> None:
        if not self._connected or self._connection is None:
            raise AdapterError("Not connected")

        text_turns = [t for t in turns if t.text is not None]
        recent = text_turns[-self._max_history_turns :]

        for turn in recent:
            if turn.role == "user":
                role = "user"
                content_type = "input_text"
            else:
                role = "assistant"
                content_type = "output_text"

            try:
                await self._connection.conversation.item.create(
                    item={
                        "type": "message",
                        "role": role,
                        "content": [{"type": content_type, "text": turn.text}],
                    }
                )
            except Exception as exc:
                raise AdapterError(f"Failed to restore history turn: {exc}") from exc

    @property
    def is_connected(self) -> bool:
        return self._connected


def _parse_json_args(raw: str) -> dict[str, Any]:
    """Parse JSON arguments string, returning empty dict on failure."""
    import json

    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(result, dict):
        return {}
    return result
