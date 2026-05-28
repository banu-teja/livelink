"""Terminal supervisor UI: mission-control display for realtime agent supervision.

Renders a structured terminal interface using ANSI escapes and Unicode box-drawing.
No external dependencies beyond Python stdlib. Designed for 80-column terminals.

Layout (top to bottom):
  - Header: session state bar (model, status, turn count)
  - Pending decisions: highlighted action items needing human response
  - Event timeline: scrolling log with timestamps and color-coded events
  - Input prompt: non-interrupting command entry at the bottom
"""

from __future__ import annotations

import asyncio
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

# ---------------------------------------------------------------------------
# ANSI color scheme
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"

# Foreground colors (semantic)
_FG_CYAN = "\033[36m"       # session/system events
_FG_GREEN = "\033[32m"      # success, approvals, completions
_FG_YELLOW = "\033[33m"     # warnings, pending decisions
_FG_RED = "\033[31m"        # errors, rejections
_FG_MAGENTA = "\033[35m"    # tool execution
_FG_BLUE = "\033[34m"       # progress/narration
_FG_WHITE = "\033[37m"      # default text

# Background accents (for pending decision highlight)
_BG_YELLOW = "\033[43m"
_BG_RED = "\033[41m"

# Event type to color mapping
_EVENT_COLORS: dict[str, str] = {
    "session": _FG_CYAN,
    "tool_start": _FG_MAGENTA,
    "tool_end": _FG_GREEN,
    "tool_error": _FG_RED,
    "approval": f"{_BOLD}{_FG_YELLOW}",
    "approval_resolved": _FG_GREEN,
    "workflow_start": _FG_CYAN,
    "workflow_progress": _FG_BLUE,
    "workflow_complete": _FG_GREEN,
    "workflow_fail": _FG_RED,
    "workflow_cancel": _FG_RED,
    "turn": _DIM + _FG_WHITE,
    "input": _FG_YELLOW,
    "info": _FG_WHITE,
}

# Box-drawing characters
_H = "\u2500"   # horizontal
_V = "\u2502"   # vertical
_TL = "\u250c"  # top-left
_TR = "\u2510"  # top-right
_BL = "\u2514"  # bottom-left
_BR = "\u2518"  # bottom-right
_T = "\u252c"   # T-down
_B = "\u2534"   # T-up
_BULLET = "\u2022"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimelineEntry:
    timestamp: float
    category: str
    text: str


@dataclass(frozen=True)
class PendingDecision:
    request_id: str
    question: str
    options: list[str] | None = None
    created_at: float = field(default_factory=time.time)


@dataclass
class SessionState:
    model: str = ""
    status: Literal["idle", "listening", "thinking", "speaking", "supervising"] = "idle"
    turn_count: int = 0
    session_id: str = ""
    agent_name: str = ""


# ---------------------------------------------------------------------------
# Renderer (pure display logic, no I/O management)
# ---------------------------------------------------------------------------


class TerminalRenderer:
    """Renders the supervisor UI frame. Stateless per-render; call render() to redraw."""

    def __init__(self, *, width: int = 80, timeline_height: int = 12) -> None:
        self._width = width
        self._timeline_height = timeline_height

    def render_frame(
        self,
        state: SessionState,
        pending: list[PendingDecision],
        timeline: list[TimelineEntry],
        input_buffer: str = "",
    ) -> str:
        """Build the full frame as a string. Caller writes to stdout."""
        lines: list[str] = []

        # Header: session state bar
        lines.extend(self._render_header(state))
        lines.append("")

        # Pending decisions (only if any exist)
        if pending:
            lines.extend(self._render_pending(pending))
            lines.append("")

        # Event timeline
        lines.extend(self._render_timeline(timeline))
        lines.append("")

        # Input prompt
        lines.append(self._render_input(input_buffer))

        return "\n".join(lines)

    def _render_header(self, state: SessionState) -> list[str]:
        w = self._width
        status_icon = {
            "idle": f"{_DIM}*{_RESET}",
            "listening": f"{_FG_GREEN}{_BULLET}{_RESET}",
            "thinking": f"{_FG_YELLOW}{_BULLET}{_RESET}",
            "speaking": f"{_FG_CYAN}{_BULLET}{_RESET}",
            "supervising": f"{_FG_MAGENTA}{_BULLET}{_RESET}",
        }.get(state.status, f"{_DIM}?{_RESET}")

        model_display = state.model or "no model"
        agent_display = state.agent_name or "agent"

        top_border = f"{_DIM}{_TL}{_H * (w - 2)}{_TR}{_RESET}"
        bottom_border = f"{_DIM}{_BL}{_H * (w - 2)}{_BR}{_RESET}"

        left = f" {status_icon} {_BOLD}{agent_display}{_RESET} {_DIM}({model_display}){_RESET}"
        right = f"turn {state.turn_count}  {_DIM}{state.status.upper()}{_RESET} "

        # Pad center (accounting for ANSI escape lengths)
        visible_left = len(f" * {agent_display} ({model_display})")
        visible_right = len(f"turn {state.turn_count}  {state.status.upper()} ")
        padding = w - 2 - visible_left - visible_right
        padding = max(padding, 1)

        content = f"{_DIM}{_V}{_RESET}{left}{' ' * padding}{right}{_DIM}{_V}{_RESET}"

        return [top_border, content, bottom_border]

    def _render_pending(self, pending: list[PendingDecision]) -> list[str]:
        lines: list[str] = []
        header = f" {_BOLD}{_FG_YELLOW}PENDING DECISIONS ({len(pending)}){_RESET}"
        lines.append(header)

        for i, decision in enumerate(pending[:3]):
            age = time.time() - decision.created_at
            age_str = f"{age:.0f}s ago" if age < 60 else f"{age / 60:.0f}m ago"
            prefix = f"  {_FG_YELLOW}{_BOLD}>{_RESET} "
            options_str = ""
            if decision.options:
                options_str = f" {_DIM}[{' / '.join(decision.options)}]{_RESET}"
            lines.append(f"{prefix}{decision.question}{options_str} {_DIM}({age_str}){_RESET}")

        if len(pending) > 3:
            lines.append(f"  {_DIM}... and {len(pending) - 3} more{_RESET}")

        return lines

    def _render_timeline(self, timeline: list[TimelineEntry]) -> list[str]:
        lines: list[str] = []
        header = f" {_BOLD}EVENT TIMELINE{_RESET}"
        lines.append(header)
        lines.append(f" {_DIM}{_H * (self._width - 2)}{_RESET}")

        visible = timeline[-self._timeline_height :]
        if not visible:
            lines.append(f"  {_DIM}(no events yet){_RESET}")
            return lines

        for entry in visible:
            ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
            color = _EVENT_COLORS.get(entry.category, _FG_WHITE)
            # Truncate text to fit width: timestamp(8) + space(1) + pipe(1) + space(1) = 11
            max_text = self._width - 13
            text = entry.text[:max_text] if len(entry.text) > max_text else entry.text
            lines.append(f"  {_DIM}{ts}{_RESET} {_DIM}{_V}{_RESET} {color}{text}{_RESET}")

        return lines

    def _render_input(self, input_buffer: str) -> str:
        prompt = f"{_BOLD}{_FG_CYAN}>{_RESET} "
        return f"{prompt}{input_buffer}"


# ---------------------------------------------------------------------------
# SupervisorUI (coordinates state, rendering, and async input)
# ---------------------------------------------------------------------------


class SupervisorUI:
    """Full supervisor terminal UI with async event handling and input.

    Usage::

        ui = SupervisorUI()
        await ui.start()

        # From event handlers:
        ui.push_event("tool_start", "Calling transfer_funds(amount=500)")
        ui.add_pending("req-1", "Approve transfer_funds(amount=500)?", ["yes", "no"])
        ui.update_state(status="thinking", turn_count=3)

        # When done:
        await ui.stop()
    """

    def __init__(self, *, width: int = 80, on_input: Callable[[str], Any] | None = None) -> None:
        self._renderer = TerminalRenderer(width=width)
        self._state = SessionState()
        self._pending: list[PendingDecision] = []
        self._timeline: deque[TimelineEntry] = deque(maxlen=200)
        self._input_buffer = ""
        self._on_input = on_input
        self._running = False
        self._render_lock = asyncio.Lock()
        self._input_task: asyncio.Task[None] | None = None

    @property
    def state(self) -> SessionState:
        return self._state

    def update_state(self, **kwargs: Any) -> None:
        """Update session state fields and trigger redraw."""
        for key, value in kwargs.items():
            if hasattr(self._state, key):
                setattr(self._state, key, value)

    def push_event(self, category: str, text: str) -> None:
        """Add an event to the timeline and trigger redraw."""
        self._timeline.append(TimelineEntry(timestamp=time.time(), category=category, text=text))

    def add_pending(
        self, request_id: str, question: str, options: list[str] | None = None
    ) -> None:
        """Add a pending decision requiring human input."""
        self._pending.append(PendingDecision(
            request_id=request_id, question=question, options=options
        ))

    def resolve_pending(self, request_id: str) -> None:
        """Remove a resolved pending decision."""
        self._pending = [p for p in self._pending if p.request_id != request_id]

    async def start(self) -> None:
        """Enter alternate screen and begin render loop."""
        self._running = True
        # Enter alternate screen buffer
        sys.stdout.write("\033[?1049h")
        # Hide cursor
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()
        self._input_task = asyncio.create_task(self._input_loop())
        await self._redraw()

    async def stop(self) -> None:
        """Restore terminal and exit alternate screen."""
        self._running = False
        if self._input_task:
            self._input_task.cancel()
            try:
                await self._input_task
            except asyncio.CancelledError:
                pass
        # Show cursor
        sys.stdout.write("\033[?25h")
        # Exit alternate screen
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()

    async def redraw(self) -> None:
        """Public redraw trigger (debounced internally)."""
        await self._redraw()

    async def _redraw(self) -> None:
        """Render the full frame to stdout."""
        async with self._render_lock:
            frame = self._renderer.render_frame(
                state=self._state,
                pending=self._pending,
                timeline=list(self._timeline),
                input_buffer=self._input_buffer,
            )
            # Move cursor to top-left, clear screen, write frame
            sys.stdout.write("\033[H\033[2J")
            sys.stdout.write(frame)
            # Position cursor at input line
            sys.stdout.write("\033[?25h")
            sys.stdout.flush()

    async def _input_loop(self) -> None:
        """Read stdin lines in a thread to avoid blocking the event loop."""
        loop = asyncio.get_running_loop()
        while self._running:
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                line = line.strip()
                if line and self._on_input:
                    result = self._on_input(line)
                    if asyncio.iscoroutine(result):
                        await result
                await self._redraw()
            except (EOFError, asyncio.CancelledError):
                break
