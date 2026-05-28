"""SessionConfig: frozen runtime configuration for supervised sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from relaykit.supervision.cancellation import CancellationToken
    from relaykit.supervision.events import EventBus
    from relaykit.supervision.hitl import ApprovalGate, InputManager


@dataclass(frozen=True)
class SessionConfig:
    """Runtime configuration for a RealtimeSession.

    When ``supervision=True``, components are auto-created if not provided.
    When ``supervision=False`` (default), all supervision components are ignored
    and the session behaves identically to the unsupervised path.
    """

    supervision: bool = False

    event_bus: EventBus | None = None
    cancellation_token: CancellationToken | None = None
    input_manager: InputManager | None = None
    approval_gate: ApprovalGate | None = None

    approval_timeout: float = 30.0
    approval_timeout_action: Literal["deny", "proceed"] = "deny"
