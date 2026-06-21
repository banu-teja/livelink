"""Lifecycle hooks for LiveAgent sessions.

Override any subset of methods to observe or modify session behavior.
All methods are async and have no-op default implementations.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from livelink.session import RealtimeSession
    from livelink.types import ConversationTurn


class AgentHooks:
    """Base class for agent lifecycle hooks.

    Override the methods you care about. All are optional.

    Usage::

        class MyHooks(AgentHooks):
            async def on_session_start(self, session):
                logger.info("Session started: %s", session.agent.model)

            async def on_tool_error(self, name, error):
                sentry.capture_exception(error)

        agent = LiveAgent(model="...", hooks=MyHooks())
    """

    async def on_session_start(self, session: RealtimeSession) -> None:
        """Called when a session connects to the provider."""

    async def on_session_end(self, session: RealtimeSession) -> None:
        """Called when a session is closed (gracefully or not)."""

    async def on_turn_start(self, role: str) -> None:
        """Called when a new turn begins (role: 'user' or 'model')."""

    async def on_turn_end(self, turn: ConversationTurn) -> None:
        """Called when a turn completes."""

    async def on_tool_start(self, name: str, args: dict[str, Any]) -> None:
        """Called before a tool is executed."""

    async def on_tool_end(self, name: str, result: str) -> None:
        """Called after a tool returns successfully."""

    async def on_tool_error(self, name: str, error: Exception) -> None:
        """Called when a tool raises an exception."""

    async def on_interrupt(self) -> None:
        """Called when the model's generation is interrupted."""

    async def on_error(self, error: Exception) -> None:
        """Called on any unhandled error during the session."""
