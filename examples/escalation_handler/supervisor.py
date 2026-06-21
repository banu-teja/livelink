"""Rich terminal supervisor for collaborative realtime oversight.

Connects to a running agent session and provides an operational supervision
interface — ambient awareness of investigation progress with focused
intervention when needed.

Commands:
  yes/y              Approve pending action
  no/n               Reject pending action
  inject <text>      Push context the agent will incorporate at next checkpoint
  summarize          Ask agent to summarize current findings (sugar for inject)
  reprioritize <x>   Redirect the agent's investigation focus
  cancel             Cooperative shutdown of the session
  inspect            Session state snapshot
  quit/q             Disconnect (session continues without supervisor)

Usage: uv run python examples/escalation_handler/supervisor.py <session_id>
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime


# ---------------------------------------------------------------------------
# ANSI formatting — zero external dependencies
# ---------------------------------------------------------------------------


class _C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _badge(text: str, color: str) -> str:
    return f"{color}{_C.BOLD} {text} {_C.RESET}"


def _box(title: str, lines: list[str], color: str = _C.CYAN) -> str:
    width = max(len(title) + 4, max((len(ln) for ln in lines), default=40) + 4, 50)
    top = f"  {color}┌{'─' * (width - 2)}┐{_C.RESET}"
    title_line = f"  {color}│{_C.RESET} {_C.BOLD}{title}{_C.RESET}{' ' * (width - len(title) - 4)}{color}│{_C.RESET}"
    sep = f"  {color}├{'─' * (width - 2)}┤{_C.RESET}"
    bottom = f"  {color}└{'─' * (width - 2)}┘{_C.RESET}"
    body = []
    for line in lines:
        padding = width - len(line) - 4
        body.append(f"  {color}│{_C.RESET} {line}{' ' * max(0, padding)} {color}│{_C.RESET}")
    return "\n".join([top, title_line, sep] + body + [bottom])


# ---------------------------------------------------------------------------
# UI rendering
# ---------------------------------------------------------------------------

_HEADER = f"""{_C.CYAN}{_C.BOLD}
  ╔══════════════════════════════════════════════════════════════╗
  ║        SUPERVISOR — Collaborative Realtime Oversight         ║
  ╚══════════════════════════════════════════════════════════════╝{_C.RESET}"""

_SEP = f"  {_C.DIM}{'─' * 60}{_C.RESET}"

_COMMANDS_HELP = (
    f"  {_C.DIM}Commands: "
    f"{_C.WHITE}yes{_C.DIM}/{_C.WHITE}no{_C.DIM} · "
    f"{_C.WHITE}inject{_C.DIM} <text> · "
    f"{_C.WHITE}summarize{_C.DIM} · "
    f"{_C.WHITE}reprioritize{_C.DIM} <focus> · "
    f"{_C.WHITE}cancel{_C.DIM} · "
    f"{_C.WHITE}inspect{_C.DIM} · "
    f"{_C.WHITE}quit{_C.RESET}"
)


# ---------------------------------------------------------------------------
# State tracking for ambient awareness
# ---------------------------------------------------------------------------


class _SessionState:
    __slots__ = (
        "tools_called",
        "tools_in_flight",
        "pending_approvals",
        "session_start",
        "hypothesis",
        "confidence",
        "open_questions",
        "priority",
        "evidence_count",
        "events_received",
    )

    def __init__(self) -> None:
        self.tools_called: list[str] = []
        self.tools_in_flight: set[str] = set()
        self.pending_approvals: int = 0
        self.session_start: float = 0.0
        self.hypothesis: str = ""
        self.confidence: int = 0
        self.open_questions: str = ""
        self.priority: str = ""
        self.evidence_count: int = 0
        self.events_received: int = 0


_state = _SessionState()


def _parse_investigation_status(result_text: str) -> None:
    for line in result_text.split("\n"):
        line = line.strip()
        if line.startswith("Hypothesis:"):
            _state.hypothesis = line[11:].strip()
        elif line.startswith("Confidence:"):
            try:
                _state.confidence = int(line[11:].strip().rstrip("%"))
            except ValueError:
                pass
        elif line.startswith("Open questions:"):
            _state.open_questions = line[15:].strip()
        elif line.startswith("Priority:"):
            _state.priority = line[9:].strip()
        elif line.startswith("Evidence:"):
            parts = line[9:].strip()
            _state.evidence_count = len([p for p in parts.split(",") if p.strip()])


def _render_investigation_panel(ts: str) -> None:
    conf = _state.confidence
    if conf >= 70:
        conf_color = _C.GREEN
    elif conf >= 40:
        conf_color = _C.YELLOW
    else:
        conf_color = _C.RED
    conf_bar_filled = conf // 5
    conf_bar = (
        f"{conf_color}{'█' * conf_bar_filled}{_C.DIM}{'░' * (20 - conf_bar_filled)}{_C.RESET}"
    )

    priority_colors = {
        "investigating": _C.BLUE,
        "mitigating": _C.YELLOW,
        "escalating": _C.RED,
        "resolving": _C.GREEN,
    }
    p_color = priority_colors.get(_state.priority, _C.WHITE)

    print(f"\n  {_C.CYAN}┌{'─' * 58}┐{_C.RESET}")
    print(
        f"  {_C.CYAN}│{_C.RESET} {_C.BOLD}INVESTIGATION STATUS{_C.RESET}{' ' * 24}{_C.DIM}{ts}{_C.RESET} {_C.CYAN}│{_C.RESET}"
    )
    print(f"  {_C.CYAN}├{'─' * 58}┤{_C.RESET}")
    print(
        f"  {_C.CYAN}│{_C.RESET}  Hypothesis:  {_C.WHITE}{_state.hypothesis[:40]}{_C.RESET}{' ' * max(0, 40 - len(_state.hypothesis[:40]))}   {_C.CYAN}│{_C.RESET}"
    )
    if len(_state.hypothesis) > 40:
        print(
            f"  {_C.CYAN}│{_C.RESET}               {_C.DIM}{_state.hypothesis[40:80]}{_C.RESET}{' ' * max(0, 40 - len(_state.hypothesis[40:80]))}   {_C.CYAN}│{_C.RESET}"
        )
    print(
        f"  {_C.CYAN}│{_C.RESET}  Confidence:  [{conf_bar}] {conf_color}{conf}%{_C.RESET}{' ' * (3 - len(str(conf)))}   {_C.CYAN}│{_C.RESET}"
    )
    print(
        f"  {_C.CYAN}│{_C.RESET}  Priority:    {p_color}{_state.priority}{_C.RESET}{' ' * max(0, 43 - len(_state.priority))}   {_C.CYAN}│{_C.RESET}"
    )
    print(
        f"  {_C.CYAN}│{_C.RESET}  Evidence:    {_state.evidence_count} signals collected{' ' * 27}   {_C.CYAN}│{_C.RESET}"
    )
    if _state.open_questions:
        q_display = _state.open_questions[:42]
        print(
            f"  {_C.CYAN}│{_C.RESET}  Questions:   {_C.YELLOW}{q_display}{_C.RESET}{' ' * max(0, 40 - len(q_display))}   {_C.CYAN}│{_C.RESET}"
        )
    print(f"  {_C.CYAN}└{'─' * 58}┘{_C.RESET}\n")


# ---------------------------------------------------------------------------
# Event rendering
# ---------------------------------------------------------------------------


def render_event(msg: dict) -> None:
    event_type = msg.get("event_type", "")
    payload = msg.get("payload", {})
    ts = _ts()

    if event_type == "ToolApprovalRequested":
        _state.pending_approvals += 1
        tool = payload.get("tool_name", "?")
        args = payload.get("arguments", {})
        print(f"\n{_SEP}")
        print(f"  {_badge('⚠ APPROVAL REQUIRED', _C.BG_RED + _C.WHITE)}")
        print(f"  {_C.DIM}{ts}{_C.RESET}  Tool: {_C.BOLD}{tool}{_C.RESET}")
        print()
        for k, v in args.items():
            v_str = str(v)
            if len(v_str) > 70:
                v_str = v_str[:67] + "..."
            print(f"    {_C.YELLOW}{k}{_C.RESET}: {v_str}")
        print()
        print(
            f"  {_C.BOLD}→ Approve ({_C.GREEN}yes{_C.RESET}{_C.BOLD}) or reject ({_C.RED}no{_C.RESET}{_C.BOLD})?{_C.RESET}"
        )
        print(f"{_SEP}\n")
        return

    if event_type == "InputRequested":
        question = payload.get("question", "")
        options = payload.get("options", [])
        print(f"\n{_SEP}")
        print(f"  {_badge('? AGENT ASKING', _C.BG_YELLOW + _C.WHITE)}")
        print(f"  {_C.DIM}{ts}{_C.RESET}  {_C.BOLD}{question}{_C.RESET}")
        if options:
            print(f"  Options: {', '.join(options)}")
        print(f"  {_C.BOLD}→ Type your response{_C.RESET}")
        print(f"{_SEP}\n")
        return

    if event_type == "ToolExecutionStarted":
        tool = payload.get("tool_name", "?")
        _state.tools_in_flight.add(tool)
        print(f"  {_C.DIM}{ts}{_C.RESET}  {_C.BLUE}▶{_C.RESET} {tool}")
        return

    if event_type == "ToolExecutionCompleted":
        tool = payload.get("tool_name", "?")
        _state.tools_in_flight.discard(tool)
        _state.tools_called.append(tool)
        _state.events_received += 1
        result_text = payload.get("result", "")
        duration = payload.get("duration_ms", 0)
        dur_str = f" {_C.DIM}({duration:.0f}ms){_C.RESET}" if duration else ""

        if tool == "update_investigation_status":
            _parse_investigation_status(result_text)
            _render_investigation_panel(ts)
            return

        print(f"  {_C.DIM}{ts}{_C.RESET}  {_C.GREEN}✓{_C.RESET} {tool}{dur_str}")
        if result_text:
            lines = result_text.split("\n")
            for line in lines[:4]:
                print(f"  {_C.DIM}    │ {line[:72]}{_C.RESET}")
            if len(lines) > 4:
                print(f"  {_C.DIM}    │ ... ({len(lines) - 4} more lines){_C.RESET}")

        if "CONFLICTING SIGNAL" in result_text:
            print(f"  {_C.YELLOW}    ⚡ Conflicting signals detected{_C.RESET}")
        if "STALE" in result_text or "DATA FRESHNESS" in result_text:
            print(f"  {_C.YELLOW}    ⏳ Data freshness warning{_C.RESET}")
        if "PARTIAL" in result_text:
            print(f"  {_C.YELLOW}    ◐ Partial result{_C.RESET}")
        return

    if event_type == "ToolExecutionFailed":
        tool = payload.get("tool_name", "?")
        error = payload.get("error", "")
        _state.tools_in_flight.discard(tool)
        print(f"  {_C.DIM}{ts}{_C.RESET}  {_C.RED}✗ {tool}: {error[:60]}{_C.RESET}")
        return

    if event_type == "ToolApprovalResolved":
        _state.pending_approvals = max(0, _state.pending_approvals - 1)
        approved = payload.get("approved", False)
        tool = payload.get("tool_name", "?")
        icon = f"{_C.GREEN}✓" if approved else f"{_C.RED}✗"
        print(
            f"  {_C.DIM}{ts}{_C.RESET}  {icon} {tool} {'approved' if approved else 'rejected'}{_C.RESET}"
        )
        return

    if event_type == "WorkflowProgress":
        step = payload.get("step", "")
        message = payload.get("message", "")
        progress = payload.get("progress", 0)
        data = payload.get("data") or {}
        bar = ""
        if progress > 0:
            filled = int(progress * 20)
            bar = f" [{_C.GREEN}{'█' * filled}{_C.DIM}{'░' * (20 - filled)}{_C.RESET}]"
        print(f"  {_C.DIM}{ts}{_C.RESET}  {_C.CYAN}◆{_C.RESET} {_C.BOLD}{step}{_C.RESET}{bar}")
        if message:
            print(f"  {_C.DIM}    │ {_C.WHITE}{message}{_C.RESET}")
        for k, v in data.items():
            print(f"  {_C.DIM}    │ {k}: {v}{_C.RESET}")
        return

    if event_type == "SessionStarted":
        _state.session_start = msg.get("timestamp", 0)
        model = payload.get("model", "?")
        print(f"  {_C.DIM}{ts}{_C.RESET}  {_C.GREEN}●{_C.RESET} Session started ({model})")
        return

    if event_type == "SessionEnded":
        reason = payload.get("reason", "?")
        print(f"\n  {_C.DIM}{ts}{_C.RESET}  {_C.DIM}○ Session ended ({reason}){_C.RESET}")
        elapsed = len(_state.tools_called)
        print(f"  {_C.DIM}    Tools executed: {elapsed}{_C.RESET}")
        return

    if event_type in ("TurnStarted", "TurnEnded"):
        return

    print(f"  {_C.DIM}{ts}  [{event_type}] {json.dumps(payload)[:60]}{_C.RESET}")


def render_inspect(detail: dict) -> None:
    lines = [
        f"Session:   {detail.get('session_id', '?')[:16]}",
        f"Model:     {detail.get('model', '?')}",
        f"State:     {detail.get('state', '?')}",
        f"Turns:     {detail.get('turn_count', 0)}",
        f"Cancelled: {detail.get('is_cancelled', False)}",
        f"Tools called: {len(_state.tools_called)}",
    ]
    pending = detail.get("pending_approvals", [])
    if pending:
        lines.append(f"Pending approvals: {len(pending)}")
        for pa in pending:
            lines.append(f"  [{pa['request_id'][:8]}] {pa['question'][:40]}")
    else:
        lines.append("Pending approvals: none")
    print(_box("SESSION STATE", lines, _C.BLUE))
    print()


def render_ack(cmd_id: str, detail: dict) -> None:
    if detail.get("already_resolved"):
        print(f"  {_C.YELLOW}(already resolved){_C.RESET}")
    elif detail.get("already_cancelled"):
        print(f"  {_C.YELLOW}(already cancelled){_C.RESET}")
    elif detail.get("injected"):
        text = detail["injected"]
        print(f'  {_C.MAGENTA}⟫ Injected: "{text}"{_C.RESET}')
    elif "session_id" in detail:
        render_inspect(detail)


def render_error(msg: dict) -> None:
    code = msg.get("code", "?")
    message = msg.get("message", "")
    print(f"  {_C.RED}✗ Error [{code}]: {message}{_C.RESET}")


# ---------------------------------------------------------------------------
# Main supervisor loop
# ---------------------------------------------------------------------------


async def main(session_id: str) -> None:
    try:
        import websockets
    except ImportError:
        raise ImportError("Install websockets: pip install websockets") from None

    host = os.environ.get("LIVELINK_HOST", "localhost")
    port = os.environ.get("LIVELINK_PORT", "8000")
    uri = f"ws://{host}:{port}/supervise/{session_id}"

    print(_HEADER)
    print(f"\n  {_C.DIM}Connecting to {uri}...{_C.RESET}")

    try:
        ws = await websockets.connect(uri)
    except Exception as e:
        print(f"\n  {_C.RED}Connection failed: {e}{_C.RESET}")
        print("  Make sure the agent is running and the session ID is correct.")
        return

    connected = json.loads(await ws.recv())
    if connected.get("type") == "error" or "session_id" not in connected:
        print(f"\n  {_C.RED}Session not found: {session_id}{_C.RESET}")
        await ws.close()
        return

    print(f"\n  {_C.GREEN}● Connected{_C.RESET}")
    print(f"  {_C.DIM}Session:{_C.RESET} {connected['session_id']}")
    print(f"  {_C.DIM}Model:{_C.RESET}   {connected.get('model', '?')}")
    print(f"  {_C.DIM}State:{_C.RESET}   {connected.get('state', '?')}")

    replay_from = connected.get("replay_from")
    if replay_from:
        print(f"  {_C.CYAN}↻ Replay available from event history{_C.RESET}")

    pending = connected.get("pending_approvals", [])
    if pending:
        print(f"\n  {_C.YELLOW}Pending approvals ({len(pending)}):{_C.RESET}")
        for pa in pending:
            print(f"    [{pa['request_id'][:8]}] {pa['question']}")

    print(
        f"\n  {_C.DIM}Runtime: reconnect with replay · cooperative cancellation · multi-observer{_C.RESET}"
    )

    await ws.send(json.dumps({"type": "subscribe", "cmd_id": "sub-1"}))
    ack = json.loads(await ws.recv())
    if ack.get("type") == "error":
        print(f"\n  {_C.RED}Subscribe failed: {ack.get('message')}{_C.RESET}")
        await ws.close()
        return

    print()
    print(_COMMANDS_HELP)
    print(f"\n{_SEP}\n")

    async def listen() -> None:
        try:
            async for raw in ws:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")
                if msg_type == "event":
                    render_event(msg)
                elif msg_type == "ack":
                    cmd_id = msg.get("cmd_id", "")
                    detail = msg.get("detail", {})
                    if detail and cmd_id not in ("sub-1", "r-check"):
                        render_ack(cmd_id, detail)
                elif msg_type == "error":
                    render_error(msg)
        except Exception:
            print(f"\n  {_C.DIM}Connection closed.{_C.RESET}")

    async def commands() -> None:
        loop = asyncio.get_running_loop()
        cmd_counter = 0

        while True:
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
            except (EOFError, KeyboardInterrupt):
                break

            line = line.strip()
            if not line:
                continue

            cmd_counter += 1
            cmd_id = f"cmd-{cmd_counter}"

            lower = line.lower()

            if lower in ("quit", "q", "exit"):
                print(f"  {_C.DIM}Disconnecting (session continues)...{_C.RESET}")
                await ws.close()
                return

            elif lower == "inspect":
                await ws.send(json.dumps({"type": "inspect", "cmd_id": cmd_id}))

            elif lower == "cancel":
                await ws.send(
                    json.dumps(
                        {
                            "type": "cancel",
                            "cmd_id": cmd_id,
                            "reason": "supervisor_cancelled",
                        }
                    )
                )
                print(f"  {_C.YELLOW}⊘ Cancel requested — propagating to session...{_C.RESET}")
                print(
                    f"  {_C.DIM}  Cancellation is cooperative: agent will finish current tool,{_C.RESET}"
                )
                print(
                    f"  {_C.DIM}  then stop gracefully. Pending approvals auto-cancelled.{_C.RESET}"
                )

            elif lower in ("yes", "y"):
                await _resolve_pending(ws, "Yes", cmd_id)

            elif lower in ("no", "n"):
                await _resolve_pending(ws, "No", cmd_id)

            elif lower == "summarize":
                await _inject(
                    ws,
                    "Please summarize your current findings: what do you know, what are you investigating, and your confidence level.",
                    cmd_id,
                )

            elif lower.startswith("reprioritize "):
                focus = line[13:].strip()
                if focus:
                    await _inject(
                        ws,
                        f"PRIORITY CHANGE: Shift investigation focus to: {focus}. Acknowledge and adapt.",
                        cmd_id,
                    )
                else:
                    print(f"  {_C.DIM}Usage: reprioritize <new focus>{_C.RESET}")

            elif lower.startswith("inject "):
                text = line[7:].strip()
                if text:
                    await _inject(ws, text, cmd_id)
                else:
                    print(f"  {_C.DIM}Usage: inject <context text>{_C.RESET}")

            else:
                print(_COMMANDS_HELP)

    try:
        await asyncio.gather(listen(), commands())
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        if not ws.close_code:
            await ws.close()
        print(f"\n  {_C.DIM}Supervisor disconnected.{_C.RESET}")


async def _inject(ws, text: str, cmd_id: str) -> None:
    await ws.send(json.dumps({"type": "inject", "cmd_id": cmd_id, "text": text}))


async def _resolve_pending(ws, answer: str, cmd_id: str) -> None:
    await ws.send(json.dumps({"type": "inspect", "cmd_id": "r-check"}))
    try:
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=3.0))
    except (asyncio.TimeoutError, Exception):
        print(f"  {_C.RED}Could not check pending state.{_C.RESET}")
        return

    pending = resp.get("detail", {}).get("pending_approvals", [])
    if not pending:
        print(f"  {_C.YELLOW}No pending approvals.{_C.RESET}")
        return

    rid = pending[0]["request_id"]
    await ws.send(
        json.dumps(
            {
                "type": "resolve",
                "cmd_id": cmd_id,
                "request_id": rid,
                "answer": answer,
            }
        )
    )
    short = answer if len(answer) <= 40 else answer[:37] + "..."
    icon = (
        _C.GREEN + "✓"
        if answer.lower() in ("yes", "y")
        else _C.RED + "✗"
        if answer.lower() in ("no", "n")
        else _C.MAGENTA + "⟫"
    )
    print(f"  {icon} Resolved [{rid[:8]}] → {short}{_C.RESET}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"  {_C.RED}Usage: python supervisor.py <session_id>{_C.RESET}")
        print(f"  {_C.DIM}Get the session ID from the agent's startup log.{_C.RESET}")
        sys.exit(1)
    try:
        asyncio.run(main(sys.argv[1]))
    except KeyboardInterrupt:
        print(f"\n  {_C.DIM}Interrupted.{_C.RESET}")
