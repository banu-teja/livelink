"""Runner: session lifecycle manager and core runtime entry point.

Provides structured execution with event-based observation.
agent.serve() uses Runner internally — there is one runtime path.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, TYPE_CHECKING

from livelink import events
from livelink.hooks import AgentHooks
from livelink.session_config import SessionConfig
from livelink.types import ConversationTurn, LiveResponse

if TYPE_CHECKING:
    from livelink.agent import LiveAgent
    from livelink.session import RealtimeSession
    from livelink.transport import Transport

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunResult:
    """Immutable result of a Runner.run() invocation."""

    history: tuple[ConversationTurn, ...] = ()
    turn_count: int = 0
    session_state: dict[str, Any] = field(default_factory=dict)
    final_response: LiveResponse | None = None
    stopped_reason: Literal["completed", "max_turns", "transport_closed", "cancelled", "error"] = (
        "completed"
    )


class _CallbackHooks(AgentHooks):
    """Adapts flat callback kwargs into AgentHooks, merged with base hooks."""

    def __init__(
        self,
        base: AgentHooks | None = None,
        *,
        on_session_start: Callable[..., Any] | None = None,
        on_session_end: Callable[..., Any] | None = None,
        on_turn_start: Callable[..., Any] | None = None,
        on_turn_end: Callable[..., Any] | None = None,
        on_tool_start: Callable[..., Any] | None = None,
        on_tool_end: Callable[..., Any] | None = None,
        on_tool_error: Callable[..., Any] | None = None,
        on_interrupt: Callable[..., Any] | None = None,
        on_error: Callable[..., Any] | None = None,
    ) -> None:
        self._base = base
        self._on_session_start = on_session_start
        self._on_session_end = on_session_end
        self._on_turn_start = on_turn_start
        self._on_turn_end = on_turn_end
        self._on_tool_start = on_tool_start
        self._on_tool_end = on_tool_end
        self._on_tool_error = on_tool_error
        self._on_interrupt = on_interrupt
        self._on_error = on_error

    async def _call(self, fn: Callable[..., Any] | None, *args: Any) -> None:
        if fn is None:
            return
        result = fn(*args)
        if asyncio.iscoroutine(result):
            await result

    async def on_session_start(self, session: RealtimeSession) -> None:
        if self._base:
            await self._base.on_session_start(session)
        await self._call(self._on_session_start, session)

    async def on_session_end(self, session: RealtimeSession) -> None:
        if self._base:
            await self._base.on_session_end(session)
        await self._call(self._on_session_end, session)

    async def on_turn_start(self, role: str) -> None:
        if self._base:
            await self._base.on_turn_start(role)
        await self._call(self._on_turn_start, role)

    async def on_turn_end(self, turn: ConversationTurn) -> None:
        if self._base:
            await self._base.on_turn_end(turn)
        await self._call(self._on_turn_end, turn)

    async def on_tool_start(self, name: str, args: dict[str, Any]) -> None:
        if self._base:
            await self._base.on_tool_start(name, args)
        await self._call(self._on_tool_start, name, args)

    async def on_tool_end(self, name: str, result: str) -> None:
        if self._base:
            await self._base.on_tool_end(name, result)
        await self._call(self._on_tool_end, name, result)

    async def on_tool_error(self, name: str, error: Exception) -> None:
        if self._base:
            await self._base.on_tool_error(name, error)
        await self._call(self._on_tool_error, name, error)

    async def on_interrupt(self) -> None:
        if self._base:
            await self._base.on_interrupt()
        await self._call(self._on_interrupt)

    async def on_error(self, error: Exception) -> None:
        if self._base:
            await self._base.on_error(error)
        await self._call(self._on_error, error)


class Runner:
    """Session lifecycle manager and core runtime entry point.

    Manages agent session execution with structured results and
    event-based observation. agent.serve() uses Runner internally.

    Usage::

        result = await Runner.run(agent, transport, max_turns=10)

    With observation callbacks::

        result = await Runner.run(
            agent, transport,
            on_tool_start=lambda name, args: print(f"Calling {name}"),
            max_turns=5,
        )

    Text-only (for testing)::

        result = await Runner.run(agent, input="What's the weather?")
    """

    @staticmethod
    async def run(
        agent: LiveAgent,
        transport: Transport | None = None,
        *,
        input: str | None = None,
        deps: Any = None,
        config: SessionConfig | None = None,
        max_turns: int | None = None,
        max_history: int | None = None,
        max_handoffs: int = 10,
        on_session_start: Callable[..., Any] | None = None,
        on_session_end: Callable[..., Any] | None = None,
        on_turn_start: Callable[..., Any] | None = None,
        on_turn_end: Callable[..., Any] | None = None,
        on_tool_start: Callable[..., Any] | None = None,
        on_tool_end: Callable[..., Any] | None = None,
        on_tool_error: Callable[..., Any] | None = None,
        on_interrupt: Callable[..., Any] | None = None,
        on_error: Callable[..., Any] | None = None,
        on_handoff: Callable[..., Any] | None = None,
    ) -> RunResult:
        """Run an agent session to completion.

        Args:
            agent: The agent to run.
            transport: Transport for I/O. If None, uses input param with MemoryTransport.
            input: Text input for single-turn text-only mode (requires transport=None).
            deps: Dependency injection object passed to tools via ToolContext.
            config: Session configuration. If None, uses defaults.
            max_turns: Maximum LLM turns before stopping. None = unlimited.
            max_history: Maximum conversation turns to retain. Oldest truncated first.
            max_handoffs: Maximum agent handoffs per run (prevents infinite loops).
            on_session_start: Called when session connects.
            on_session_end: Called when session closes.
            on_turn_start: Called when a new turn begins (role: str).
            on_turn_end: Called when a turn completes (turn: ConversationTurn).
            on_tool_start: Called before tool execution (name: str, args: dict).
            on_tool_end: Called after tool completes (name: str, result: str).
            on_tool_error: Called on tool error (name: str, error: Exception).
            on_interrupt: Called on model interruption.
            on_error: Called on unhandled errors.
            on_handoff: Called when agent handoff occurs (from_agent, to_agent, reason).

        Returns:
            RunResult with session history, turn count, and stop reason.
        """
        from livelink.handoff import parse_handoff_result
        from livelink.transport import MemoryTransport

        if transport is None and input is None:
            raise ValueError("Either transport or input must be provided")
        if transport is not None and input is not None:
            raise ValueError("Cannot provide both transport and input")

        if transport is None:
            mem_transport = MemoryTransport()
            mem_transport.queue_text(input)  # type: ignore[arg-type]
            mem_transport.queue_close()
            transport = mem_transport

        has_callbacks = any(
            [
                on_session_start,
                on_session_end,
                on_turn_start,
                on_turn_end,
                on_tool_start,
                on_tool_end,
                on_tool_error,
                on_interrupt,
                on_error,
                on_handoff,
            ]
        )

        current_agent = agent
        all_history: list[ConversationTurn] = []
        total_turns = 0
        handoff_count = 0
        stopped_reason: Literal[
            "completed", "max_turns", "transport_closed", "cancelled", "error"
        ] = "completed"

        while True:
            hooks: AgentHooks | None = None
            if has_callbacks or current_agent.hooks:
                hooks = _CallbackHooks(
                    base=current_agent.hooks,
                    on_session_start=on_session_start,
                    on_session_end=on_session_end,
                    on_turn_start=on_turn_start,
                    on_turn_end=on_turn_end,
                    on_tool_start=on_tool_start,
                    on_tool_end=on_tool_end,
                    on_tool_error=on_tool_error,
                    on_interrupt=on_interrupt,
                    on_error=on_error,
                )

            session = _create_session(current_agent, deps=deps, config=config, hooks=hooks)

            if max_turns is not None:
                remaining = max_turns - total_turns
                if remaining <= 0:
                    stopped_reason = "max_turns"
                    break
                session._max_turns = remaining  # noqa: SLF001

            try:
                await session.run(transport)
            except Exception as exc:
                events.error_occurred(
                    session.session_id,
                    type(exc).__name__,
                    str(exc),
                    recoverable=False,
                )
                stopped_reason = "error"
                all_history.extend(session.history)
                total_turns += session.turn_count
                raise

            all_history.extend(session.history)
            total_turns += session.turn_count

            if max_history is not None and len(all_history) > max_history:
                all_history = all_history[-max_history:]

            # Check for handoff
            if session._pending_handoff:  # noqa: SLF001
                handoff_count += 1
                if handoff_count > max_handoffs:
                    logger.warning("Max handoffs (%d) exceeded, stopping", max_handoffs)
                    stopped_reason = "completed"
                    break

                tool_name, reason = parse_handoff_result(session._pending_handoff)  # noqa: SLF001
                target_agent = _resolve_handoff_target(current_agent, tool_name)

                if target_agent is None:
                    logger.warning("Handoff target not found for tool %s", tool_name)
                    stopped_reason = "error"
                    break

                events.agent_handoff(session.session_id, current_agent.model, target_agent.model)

                if on_handoff:
                    result = on_handoff(current_agent, target_agent, reason)
                    if asyncio.iscoroutine(result):
                        await result

                # Execute on_handoff callback from the Handoff dataclass
                handoff_obj = _find_handoff(current_agent, tool_name)
                if handoff_obj and handoff_obj.on_handoff:
                    cb_result = handoff_obj.on_handoff(current_agent, target_agent, reason)
                    if asyncio.iscoroutine(cb_result):
                        await cb_result

                current_agent = target_agent
                continue

            # Normal completion — determine stop reason
            if max_turns is not None and total_turns >= max_turns:
                stopped_reason = "max_turns"
            elif session._closed:  # noqa: SLF001
                if session._cancellation_token and session._cancellation_token.is_cancelled:  # noqa: SLF001
                    stopped_reason = "cancelled"
                else:
                    stopped_reason = "transport_closed"
            break

        return RunResult(
            history=tuple(all_history),
            turn_count=total_turns,
            session_state=dict(session.session_state) if "session" in dir() else {},
            final_response=None,
            stopped_reason=stopped_reason,
        )


def _create_session(
    agent: LiveAgent,
    *,
    deps: Any = None,
    config: SessionConfig | None = None,
    hooks: AgentHooks | None = None,
) -> RealtimeSession:
    """Create a session, optionally overriding hooks."""
    from livelink.session import RealtimeSession

    object.__setattr__(agent, "_frozen", True)
    return RealtimeSession(agent=agent, deps=deps, config=config, hooks=hooks)


def _resolve_handoff_target(agent: LiveAgent, tool_name: str) -> LiveAgent | None:
    """Find the target agent for a handoff tool name."""
    for h in agent.handoffs:
        t = h.to_tool()
        if t.name == tool_name:
            return h.target
    return None


def _find_handoff(agent: LiveAgent, tool_name: str) -> Any:
    """Find the Handoff dataclass matching a tool name."""
    for h in agent.handoffs:
        t = h.to_tool()
        if t.name == tool_name:
            return h
    return None
