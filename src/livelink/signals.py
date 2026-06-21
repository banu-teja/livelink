from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class RuntimeSignal(Enum):
    """Canonical supervision-relevant state transitions.

    Only signals that matter to a supervisor, human operator,
    or conversational runtime belong here.
    """

    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"

    ESCALATION_REQUESTED = "escalation_requested"
    APPROVAL_REQUIRED = "approval_required"
    CONFIDENCE_CHANGED = "confidence_changed"
    HYPOTHESIS_UPDATED = "hypothesis_updated"
    EXECUTION_BLOCKED = "execution_blocked"
    PROGRESS_MILESTONE = "progress_milestone"

    RISK_ELEVATED = "risk_elevated"
    TIMEOUT_APPROACHING = "timeout_approaching"
    PARTIAL_FAILURE = "partial_failure"

    GUIDANCE_RECEIVED = "guidance_received"


class InterruptMode(Enum):
    """How execution interrupts surface in the conversation."""

    CONVERSATIONAL = "conversational"
    ESCALATE_SUPERVISOR = "escalate"
    DEFERRED = "deferred"
    AUTO_APPROVE = "auto_approve"


class ContextInjectionMode(Enum):
    """How signals are delivered to the live model. Internal to SupervisionRelay."""

    AMBIENT = "ambient"
    PROMPT = "prompt"
    ACK_REQUIRED = "ack_required"


@dataclass(frozen=True)
class OperationalSignal:
    """A single supervision-relevant state transition ready for injection."""

    signal: RuntimeSignal
    summary: str
    urgency: Literal["low", "medium", "high", "critical"] = "medium"
    structured_data: dict[str, Any] = field(default_factory=dict)
    source_run_id: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class OperationalContextPolicy:
    """Controls how execution state becomes conversational context."""

    watch_signals: frozenset[RuntimeSignal] = frozenset()
    debounce_ms: int = 2000
    context_window: int = 5
    interrupt_mode: InterruptMode = InterruptMode.CONVERSATIONAL
    interrupt_timeout: float = 120.0
    min_urgency: Literal["low", "medium", "high", "critical"] = "low"
