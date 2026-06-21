"""RelayKit — Unified realtime multimodal runtime across providers."""

from __future__ import annotations

from livelink.agent import AgentConfig, LiveAgent
from livelink.delegation import DelegatedBackend
from livelink.exceptions import RelayKitError
from livelink.governance import GovernancePolicy, GovernanceRule, ResolutionAuthority
from livelink.guardrails import GuardrailResult, input_guardrail, output_guardrail
from livelink.handoff import Handoff
from livelink.hooks import AgentHooks
from livelink.runner import Runner, RunResult
from livelink.session import RealtimeSession
from livelink.session_config import SessionConfig
from livelink.signals import (
    InterruptMode,
    OperationalContextPolicy,
    OperationalSignal,
    RuntimeSignal,
)
from livelink.streaming import (
    AudioDelta,
    AudioFrame,
    StreamEvent,
    StreamInterrupted,
    TextDelta,
    TurnComplete,
)
from livelink.tools import ToolContext, tool
from livelink.transport import Transport, WebSocketTransport

import livelink.adapters  # noqa: E402, F401 — triggers lazy adapter registration

__all__ = [
    "AgentConfig",
    "AgentHooks",
    "AudioDelta",
    "AudioFrame",
    "DelegatedBackend",
    "GovernancePolicy",
    "GovernanceRule",
    "GuardrailResult",
    "Handoff",
    "InterruptMode",
    "LiveAgent",
    "OperationalContextPolicy",
    "OperationalSignal",
    "RealtimeSession",
    "RelayKitError",
    "ResolutionAuthority",
    "RunResult",
    "Runner",
    "RuntimeSignal",
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
