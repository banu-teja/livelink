from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from livelink.governance import GovernancePolicy
from livelink.memory import OperationalMemory
from livelink.signals import OperationalContextPolicy

if TYPE_CHECKING:
    from livelink.relay import SupervisionRelay
    from livelink.supervision import CancellationToken, EventBus, InputManager
    from livelink.tools import Tool


class DelegationState(Enum):
    """Lifecycle states of a delegated execution."""

    IDLE = "idle"
    RUNNING = "running"
    AWAITING_INPUT = "awaiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class DelegatedBackend:
    """Binding between an execution adapter and operational context policy."""

    adapter: Any  # ExecutionAdapter protocol
    name: str
    description: str
    policy: OperationalContextPolicy = field(default_factory=OperationalContextPolicy)
    governance: GovernancePolicy = field(default_factory=GovernancePolicy)


@dataclass
class DelegationHandle:
    """Runtime state for an active or completed delegation."""

    backend_name: str
    run_id: str
    state: DelegationState
    relay: SupervisionRelay | None = None
    task: asyncio.Task[Any] | None = None
    event_bus: EventBus | None = None
    input_manager: InputManager | None = None
    cancellation_token: CancellationToken | None = None
    operational_memory: OperationalMemory = field(default_factory=OperationalMemory)
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    result: Any | None = None


_DELEGATION_PREFIX = "__delegation__:"


def _slugify(name: str) -> str:
    """Convert a backend name to a valid tool name suffix."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return slug


def generate_delegation_tool(backend: DelegatedBackend) -> Tool:
    """Generate the delegation trigger tool for a backend."""
    from livelink.tools import Tool

    slug = _slugify(backend.name)
    tool_name = f"delegate_to_{slug}"

    async def _delegate_fn(context: str) -> str:
        return f"{_DELEGATION_PREFIX}{backend.name}:{context}"

    return Tool(
        name=tool_name,
        description=f"Start: {backend.description}. Provide context about what to investigate/execute.",
        fn=_delegate_fn,
        parameters={
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Context and instructions for the delegated execution.",
                },
            },
            "required": ["context"],
        },
    )


def is_delegation_result(result: str) -> bool:
    """Check if a tool result is a delegation trigger."""
    return isinstance(result, str) and result.startswith(_DELEGATION_PREFIX)


def parse_delegation_result(result: str) -> tuple[str, str]:
    """Extract (backend_name, context) from a delegation sentinel."""
    without_prefix = result[len(_DELEGATION_PREFIX) :]
    name, _, context = without_prefix.partition(":")
    return name, context
