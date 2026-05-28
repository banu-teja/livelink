from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, AsyncIterator

try:
    from google import genai
    from google.genai import types
except ImportError as _import_err:
    raise ImportError(
        "The google-genai package is required for the Gemini adapter. "
        "Install it with: pip install relaykit[gemini]"
    ) from _import_err

from relaykit.adapters.base import BaseAdapter
from relaykit.exceptions import (
    AdapterError,
    AuthenticationError,
    ConnectionError,
)
from relaykit.types import ConversationTurn, LiveChunk, ToolCallData, ToolResponse

logger = logging.getLogger(__name__)


class GeminiLiveAdapter(BaseAdapter):
    """Gemini Live API adapter using the google-genai SDK.

    No-arg constructor — all configuration is passed via connect(config).
    """

    def __init__(self) -> None:
        self._client: genai.Client | None = None
        self._session: Any | None = None
        self._ctx_manager: Any | None = None
        self._resume_handle: str | None = None
        self._connected: bool = False
        self._is_vertex: bool = False
        self._input_sample_rate: int = 16000
        self._last_audio_time: float = 0.0

    async def connect(self, config: dict[str, Any]) -> None:
        """Connect to Gemini Live with the given configuration.

        Supported config keys:
            - model: str (e.g. "gemini-3.1-flash-audio")
            - system_instruction: str
            - voice: str (prebuilt voice name)
            - output_modalities: list[str] (e.g. ["AUDIO"])
            - tools: list[dict] (function declarations)
            - api_key: str
            - project: str (for Vertex AI)
            - location: str (for Vertex AI, defaults to "us-central1")
        """
        model = config.get("model", "gemini-3.1-flash-audio")
        system_instruction = config.get("system_instruction")
        voice = config.get("voice")
        output_modalities = config.get("output_modalities", ["AUDIO"])
        tools = config.get("tools")
        api_key = config.get("api_key") or os.environ.get("GOOGLE_API_KEY")
        project = config.get("project")
        location = config.get("location", "us-central1")
        self._input_sample_rate = config.get("input_sample_rate", 16000)

        try:
            if api_key:
                self._client = genai.Client(api_key=api_key)
                self._is_vertex = False
            else:
                resolved_project = project or os.environ.get(
                    "GOOGLE_CLOUD_PROJECT", os.environ.get("GCLOUD_PROJECT")
                )
                if not resolved_project:
                    raise AuthenticationError(
                        "GOOGLE_API_KEY environment variable not set. "
                        "Get one at https://aistudio.google.com/apikey"
                    )
                self._client = genai.Client(
                    vertexai=True, project=resolved_project, location=location
                )
                self._is_vertex = True
        except Exception as exc:
            raise AuthenticationError(f"Failed to create Gemini client: {exc}") from exc

        speech_config = None
        if voice:
            speech_config = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice,
                    )
                )
            )

        resumption = (
            types.SessionResumptionConfig(handle=self._resume_handle)
            if self._resume_handle
            else types.SessionResumptionConfig()
        )

        gemini_tools = None
        if tools:
            gemini_tools = [
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=decl["name"],
                            description=decl.get("description", ""),
                            parameters=decl.get("parameters"),
                        )
                        for decl in tools
                    ]
                )
            ]

        live_config = types.LiveConnectConfig(
            response_modalities=output_modalities,
            system_instruction=system_instruction,
            speech_config=speech_config,
            session_resumption=resumption,
            tools=gemini_tools,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow(),
            ),
        )

        try:
            self._ctx_manager = self._client.aio.live.connect(
                model=model,
                config=live_config,
            )
            self._session = await self._ctx_manager.__aenter__()
            self._connected = True
            logger.info("Connected to Gemini Live model=%s", model)
        except Exception as exc:
            self._connected = False
            self._ctx_manager = None
            self._session = None
            raise ConnectionError(f"Failed to connect to Gemini Live: {exc}") from exc

    async def disconnect(self) -> None:
        self._connected = False
        if self._ctx_manager is not None:
            try:
                await self._ctx_manager.__aexit__(None, None, None)
            except Exception as exc:
                logger.warning("Error during disconnect: %s", exc)
            finally:
                self._ctx_manager = None
                self._session = None

    async def send(self, content: str | bytes, *, mime_type: str = "audio/pcm") -> None:
        """Push content into the active Gemini session.

        For text: uses send_client_content with turn_complete=True.
        For audio bytes: uses send_realtime_input (VAD handles turn detection).
        """
        if not self._connected or self._session is None:
            raise AdapterError("Not connected. Call connect() first.")

        try:
            if isinstance(content, bytes):
                self._last_audio_time = time.monotonic()
                audio_mime = mime_type
                if "rate=" not in audio_mime:
                    audio_mime = f"{mime_type};rate={self._input_sample_rate}"
                await self._session.send_realtime_input(
                    audio=types.Blob(data=content, mime_type=audio_mime),
                )
            else:
                await self._session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part(text=content)],
                    ),
                    turn_complete=True,
                )
        except (AdapterError, AuthenticationError, ConnectionError):
            raise
        except Exception as exc:
            raise AdapterError(f"Error during send: {exc}") from exc

    async def end_audio_stream(self) -> None:
        """Signal that the audio stream has ended (explicit turn boundary).

        Only works with AI Studio (api_key) auth — not supported on Vertex AI.
        """
        if self._session is None or self._is_vertex:
            return
        try:
            await self._session.send_realtime_input(audio_stream_end=True)
        except Exception:
            logger.debug("audio_stream_end not supported or failed")

    async def receive(self) -> AsyncIterator[LiveChunk]:  # type: ignore[override]
        """Yield LiveChunk events from the Gemini session.

        Runs continuously across multiple turns until disconnect.
        After each turn_complete, starts a new receive() call for the next turn.
        """
        if not self._connected or self._session is None:
            raise AdapterError("Not connected. Call connect() first.")

        try:
            while self._connected and self._session is not None:
                async for msg in self._session.receive():
                    if not self._connected:
                        return

                    self._update_resume_handle(msg)

                    if msg.go_away:
                        yield LiveChunk(type="session_reconnecting")

                    if msg.tool_call:
                        calls = tuple(
                            ToolCallData(
                                id=fc.id or fc.name,
                                name=fc.name,
                                args=dict(fc.args) if fc.args else {},
                            )
                            for fc in msg.tool_call.function_calls
                        )
                        yield LiveChunk(type="tool_call", tool_calls=calls)
                        continue

                    if msg.tool_call_cancellation:
                        yield LiveChunk(
                            type="tool_call_cancellation",
                            tool_call_ids=tuple(msg.tool_call_cancellation.ids),
                        )
                        continue

                    if msg.server_content:
                        sc = msg.server_content
                        if getattr(sc, "interrupted", False):
                            yield LiveChunk(type="interrupted")
                            continue
                        if sc.model_turn and sc.model_turn.parts:
                            for part in sc.model_turn.parts:
                                if part.text:
                                    yield LiveChunk(type="text", text=part.text)
                                if part.inline_data and part.inline_data.data:
                                    yield LiveChunk(
                                        type="audio",
                                        audio=part.inline_data.data,
                                    )
                        if getattr(sc, "output_transcription", None):
                            text = getattr(sc.output_transcription, "text", None)
                            if text:
                                yield LiveChunk(type="transcript", text=text)
                        if getattr(sc, "input_transcription", None):
                            text = getattr(sc.input_transcription, "text", None)
                            if text:
                                yield LiveChunk(type="input_transcript", text=text)
                        if sc.turn_complete:
                            yield LiveChunk(type="turn_end")
                            break  # Exit inner loop, continue outer while loop
        except (AdapterError, AuthenticationError, ConnectionError):
            raise
        except Exception as exc:
            if not self._connected:
                return
            raise AdapterError(f"Error in receive loop: {exc}") from exc

    async def cancel_response(self) -> None:
        """Cancel current generation (no-op if session unavailable)."""
        if self._session is None:
            return
        with _suppress(Exception):
            await self._session.send_client_content(
                turns=types.Content(role="user", parts=[]),
                turn_complete=True,
            )

    async def send_tool_response(self, responses: list[ToolResponse]) -> None:
        if not self._connected or self._session is None:
            raise AdapterError("Not connected. Call connect() first.")

        function_responses = [
            types.FunctionResponse(
                name=r.call_id.split("_")[0] if "_" in r.call_id else r.call_id,
                id=r.call_id,
                response={"result": r.result},
            )
            for r in responses
        ]
        await self._session.send_tool_response(function_responses=function_responses)

    async def restore_history(self, turns: list[ConversationTurn]) -> None:
        if self._resume_handle is not None:
            return

        if not self._connected or self._session is None:
            raise AdapterError("Not connected. Call connect() first.")

        try:
            for turn in turns:
                if turn.text is None:
                    continue
                await self._session.send_client_content(
                    turns=types.Content(
                        role=turn.role,
                        parts=[types.Part(text=turn.text)],
                    ),
                    turn_complete=False,
                )
        except Exception as exc:
            raise AdapterError(f"Error restoring history: {exc}") from exc

    async def heartbeat_loop(self) -> None:
        """Send silent audio every 5s to keep the Gemini connection alive.

        Only fires when no user audio was received in the last 5 seconds.
        """
        silence = b"\x00" * 3200  # 100ms of silence at 16kHz PCM16
        while self._connected and self._session is not None:
            await asyncio.sleep(5.0)
            if not self._connected or self._session is None:
                break
            if time.monotonic() - self._last_audio_time < 5.0:
                continue
            try:
                await self.send(silence, mime_type="audio/pcm")
            except Exception:
                break

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _update_resume_handle(self, msg: Any) -> None:
        sru = getattr(msg, "session_resumption_update", None)
        if sru is not None:
            new_handle = getattr(sru, "new_handle", None)
            if new_handle:
                self._resume_handle = new_handle

    def get_resume_state(self) -> dict[str, Any]:
        if self._resume_handle:
            return {"resume_handle": self._resume_handle}
        return {}

    def set_resume_state(self, state: dict[str, Any]) -> None:
        handle = state.get("resume_handle")
        if handle:
            self._resume_handle = handle


class _suppress:
    """Minimal single-exception context manager to avoid contextlib import."""

    def __init__(self, *exceptions: type[BaseException]) -> None:
        self._exceptions = exceptions

    def __enter__(self) -> _suppress:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, *_: Any) -> bool:
        return exc_type is not None and issubclass(exc_type, self._exceptions)
