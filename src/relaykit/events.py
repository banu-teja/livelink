from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("relaykit.events")


@dataclass(frozen=True)
class Event:
    type: str
    session_id: str
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)


def emit(event: Event) -> None:
    """Emit a structured event as JSON to the relaykit.events logger."""
    logger.info(json.dumps(asdict(event), default=str))


def session_started(session_id: str, agent_name: str, model: str) -> None:
    emit(
        Event(
            type="session_start",
            session_id=session_id,
            data={"agent_name": agent_name, "model": model},
        )
    )


def session_ended(session_id: str, duration_ms: float, turns: int, reason: str) -> None:
    emit(
        Event(
            type="session_end",
            session_id=session_id,
            data={"duration_ms": duration_ms, "turns": turns, "reason": reason},
        )
    )


def turn_started(session_id: str, turn_number: int) -> None:
    emit(
        Event(
            type="turn_start",
            session_id=session_id,
            data={"turn_number": turn_number},
        )
    )


def turn_ended(session_id: str, turn_number: int, duration_ms: float) -> None:
    emit(
        Event(
            type="turn_end",
            session_id=session_id,
            data={"turn_number": turn_number, "duration_ms": duration_ms},
        )
    )


def tool_called(
    session_id: str,
    tool_name: str,
    duration_ms: float,
    success: bool,
    error: str | None = None,
) -> None:
    data: dict[str, Any] = {
        "tool_name": tool_name,
        "duration_ms": duration_ms,
        "success": success,
    }
    if error is not None:
        data["error"] = error
    emit(Event(type="tool_call", session_id=session_id, data=data))


def agent_handoff(session_id: str, from_agent: str, to_agent: str) -> None:
    emit(
        Event(
            type="handoff",
            session_id=session_id,
            data={"from_agent": from_agent, "to_agent": to_agent},
        )
    )


def guardrail_triggered(session_id: str, name: str, action: str) -> None:
    emit(
        Event(
            type="guardrail_triggered",
            session_id=session_id,
            data={"guardrail_name": name, "action": action},
        )
    )


def error_occurred(session_id: str, error_type: str, message: str, recoverable: bool) -> None:
    emit(
        Event(
            type="error",
            session_id=session_id,
            data={"error_type": error_type, "message": message, "recoverable": recoverable},
        )
    )
