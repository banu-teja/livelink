"""RelayKit — Unified realtime multimodal runtime across providers."""

from __future__ import annotations

from relaykit.agent import AgentConfig, LiveAgent
from relaykit.exceptions import RelayKitError
from relaykit.guardrails import GuardrailResult, input_guardrail, output_guardrail
from relaykit.handoff import Handoff
from relaykit.hooks import AgentHooks
from relaykit.runner import Runner, RunResult
from relaykit.session import RealtimeSession
from relaykit.session_config import SessionConfig
from relaykit.streaming import (
    AudioDelta,
    AudioFrame,
    StreamEvent,
    StreamInterrupted,
    TextDelta,
    TurnComplete,
)
from relaykit.tools import ToolContext, tool
from relaykit.transport import Transport, WebSocketTransport

import relaykit.adapters  # noqa: E402, F401 — triggers lazy adapter registration

__all__ = [
    "AgentConfig",
    "AgentHooks",
    "AudioDelta",
    "AudioFrame",
    "GuardrailResult",
    "Handoff",
    "LiveAgent",
    "RealtimeSession",
    "RelayKitError",
    "RunResult",
    "Runner",
    "SessionConfig",
    "StreamEvent",
    "StreamInterrupted",
    "TextDelta",
    "ToolContext",
    "Transport",
    "TurnComplete",
    "WebSocketTransport",
    "input_guardrail",
    "output_guardrail",
    "tool",
]

__version__ = "0.2.0"
