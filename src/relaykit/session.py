"""RealtimeSession: runtime instance that wires agent + transport + adapter.

This is the core orchestrator — it manages the streaming event loop,
tool execution, interruption handling, and session lifecycle.

When supervision is enabled (via SessionConfig), the session automatically:
- Emits lifecycle events to the EventBus
- Respects CancellationToken for cooperative shutdown
"""

from __future__ import annotations

import asyncio
import logging
import struct
import time
import uuid
from typing import Any

from relaykit import events
from relaykit.agent import LiveAgent
from relaykit.guardrails import run_guardrails
from relaykit.session_config import SessionConfig
from relaykit.streaming import AudioDelta, StreamInterrupted, TextDelta, TurnComplete
from relaykit.tools import ToolCall, ToolContext
from relaykit.transport import AudioInput, ControlInput, TextInput, Transport
from relaykit.types import ConversationTurn, LiveChunk

logger = logging.getLogger(__name__)


class RealtimeSession:
    """Runtime session instance. Created via ``agent.session()``.

    Manages the full lifecycle of a realtime conversation:
    - Provider connection (adapter)
    - Streaming event loop
    - Tool execution (call → execute → return → continue)
    - Interruption handling
    - History tracking
    - Supervision (when enabled): event emission, state tracking, cancellation

    Usage::

        session = agent.session(deps=my_deps)
        await session.run(transport)  # Blocks until session ends

    Supervised usage::

        from relaykit import SessionConfig
        session = agent.session(deps=my_deps, config=SessionConfig(supervision=True))
        await session.run(transport)  # Same API, events emitted automatically
    """

    def __init__(
        self,
        *,
        agent: LiveAgent,
        deps: Any = None,
        config: SessionConfig | None = None,
        hooks: Any = None,
    ) -> None:
        self._agent = agent
        self._deps = deps
        self._config = config or SessionConfig()
        self._hooks = hooks
        self._adapter: Any = None
        self._connected = False
        self._closed = False
        self._history: list[ConversationTurn] = []
        self._session_state: dict[str, Any] = {}
        self._tool_call_count: int = 0
        self._turn_count: int = 0
        self._max_turns: int | None = None
        self._session_id: str = uuid.uuid4().hex[:12]
        self._tool_context = ToolContext(
            deps=deps,
            session_state=self._session_state,
            history=self._history,
        )
        self._pending_handoff: str | None = None
        self._active_delegations: dict[str, Any] = {}
        self._session_start_time: float = 0.0
        self._turn_start_time: float | None = None
        self._turn_text_buffer: list[str] = []

        # Supervision components (auto-created when supervision=True)
        self._event_bus: Any = None
        self._state_machine: Any = None
        self._cancellation_token: Any = None
        self._input_manager: Any = None
        self._approval_gate: Any = None

        if self._config.supervision:
            self._init_supervision()

    def _init_supervision(self) -> None:
        """Auto-create supervision components not provided in config."""
        from relaykit.supervision.cancellation import CancellationToken
        from relaykit.supervision.events import EventBus
        from relaykit.supervision.hitl import ApprovalGate, InputManager

        self._event_bus = self._config.event_bus or EventBus()
        self._cancellation_token = self._config.cancellation_token or CancellationToken(
            name=f"session:{self._session_id}"
        )
        self._input_manager = self._config.input_manager or InputManager(
            default_timeout=self._config.approval_timeout,
            event_bus=self._event_bus,
        )
        self._approval_gate = self._config.approval_gate or ApprovalGate(self._input_manager)

    @property
    def agent(self) -> LiveAgent:
        return self._agent

    @property
    def config(self) -> SessionConfig:
        return self._config

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def history(self) -> list[ConversationTurn]:
        return list(self._history)

    @property
    def session_state(self) -> dict[str, Any]:
        return self._session_state

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def turn_count(self) -> int:
        return self._turn_count

    @property
    def _active_hooks(self) -> Any:
        """Resolved hooks: session-level override > agent hooks."""
        return self._hooks or self._agent.hooks

    @property
    def event_bus(self) -> Any:
        return self._event_bus

    @property
    def state_machine(self) -> Any:
        return self._state_machine

    @property
    def cancellation_token(self) -> Any:
        return self._cancellation_token

    @property
    def input_manager(self) -> Any:
        return self._input_manager

    async def run(self, transport: Transport) -> None:
        """Full lifecycle: connect to provider, bridge transport, handle tools.

        Blocks until the session is closed (by client disconnect, error, or explicit close).
        """
        self._session_start_time = time.perf_counter()
        try:
            await self._connect()
            self._register_for_supervision()
            events.session_started(self._session_id, self._agent.model, self._agent.model)
            if self._active_hooks:
                await self._active_hooks.on_session_start(self)
            await self._emit_session_started()

            await self._run_loop(transport)
        except Exception as exc:
            logger.error("Session error: %s", exc)
            if self._active_hooks:
                await self._active_hooks.on_error(exc)
            raise
        finally:
            duration_ms = (time.perf_counter() - self._session_start_time) * 1000
            reason = "closed" if self._closed else "error"
            events.session_ended(self._session_id, duration_ms, self._turn_count, reason)
            await self._emit_session_ended()
            self._unregister_from_supervision()
            await self._disconnect()
            if self._active_hooks:
                await self._active_hooks.on_session_end(self)
            await transport.close()

    async def send(self, content: str | bytes) -> None:
        """Send text or audio to the model.

        For use with manual streaming control (not ``run()``).
        """
        if not self._connected:
            raise RuntimeError("Session not connected. Call run() or connect() first.")

        if isinstance(content, str):
            await self._adapter.send(content)
        else:
            await self._adapter.send(content, mime_type="audio/pcm")

    async def interrupt(self) -> None:
        """Cancel the model's current generation."""
        if self._adapter:
            await self._adapter.cancel_response()
        if self._active_hooks:
            await self._active_hooks.on_interrupt()

    async def close(self) -> None:
        """End the session gracefully."""
        self._closed = True
        if self._cancellation_token:
            self._cancellation_token.cancel(reason="session_closed")

    # --- Internal ---

    async def _connect(self) -> None:
        """Resolve adapter from model string and connect."""
        from relaykit.registry import resolve_model

        model_info = resolve_model(self._agent.model)
        adapter_cls = model_info.adapter_class

        config = self._build_adapter_config(model_info)
        self._adapter = adapter_cls()
        await self._adapter.connect(config)
        self._connected = True

    def _build_adapter_config(self, model_info: Any) -> dict[str, Any]:
        """Build adapter configuration from agent definition and registry."""
        config: dict[str, Any] = {}

        if model_info.default_config:
            config.update(model_info.default_config)

        if self._agent.instructions:
            instructions = self._agent.instructions
            if callable(instructions):
                instructions = instructions(self._tool_context)
            config["system_instruction"] = instructions

        if self._agent.voice:
            config["voice"] = self._agent.voice

        if self._agent.tools:
            config["tools"] = self._agent.tools.declarations

        config.update(self._agent.config.provider_options)
        return config

    async def _run_loop(self, transport: Transport) -> None:
        """Main event loop: bridge transport I/O with adapter streaming.

        All tasks created here are tracked and guaranteed to be cancelled + awaited
        when the loop exits for any reason (normal completion, error, or external
        cancellation). This prevents async task leaks on provider disconnection.
        """
        tasks: list[asyncio.Task[None]] = []
        try:
            receive_task = asyncio.create_task(self._handle_input(transport))
            output_task = asyncio.create_task(self._handle_output(transport))
            heartbeat_task = asyncio.create_task(self._adapter.heartbeat_loop())
            tasks = [receive_task, output_task, heartbeat_task]

            if self._cancellation_token:
                tasks.append(asyncio.create_task(self._watch_cancellation()))

            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if receive_task in done and output_task in pending and not self._closed:
                # Input ended normally — drain remaining output with timeout
                try:
                    await asyncio.wait_for(output_task, timeout=15.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    output_task.cancel()
                    try:
                        await output_task
                    except asyncio.CancelledError:
                        pass
                # Cancel remaining background tasks (heartbeat, cancellation watcher)
                remaining = pending - {output_task}
                for task in remaining:
                    task.cancel()
                await asyncio.gather(*remaining, return_exceptions=True)
            else:
                for task in done:
                    if not task.cancelled() and task.exception() is not None:
                        logger.error("Task failed: %s", task.exception())
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
        finally:
            # Safety net: guarantee ALL tasks are cancelled and awaited on any exit
            # path, including CancelledError from external cancellation. Tasks that
            # already completed are no-ops for cancel() and gather().
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _watch_cancellation(self) -> None:
        """Wait for the cancellation token to fire, then close the session."""
        await self._cancellation_token.wait_for_cancellation()
        if not self._closed:
            logger.info("Session cancelled via token: %s", self._cancellation_token.reason)
            self._closed = True

    async def _heartbeat(self) -> None:
        """Delegate to adapter's heartbeat_loop (backward compat entry point)."""
        await self._adapter.heartbeat_loop()

    async def _handle_input(self, transport: Transport) -> None:
        """Receive input from transport and forward to adapter."""
        audio_packet_count = 0
        async for event in transport.receive():
            if self._closed:
                break
            match event:
                case TextInput(text=text):
                    logger.debug("Input: text len=%d", len(text))
                    self._transition_state("LISTENING")
                    text = await self._run_input_guardrails(text)
                    if text is None:
                        continue
                    await self._adapter.send(text)
                case AudioInput(data=data):
                    audio_packet_count += 1
                    if audio_packet_count <= 5:
                        amp = self._audio_amplitude(data)
                        logger.debug(
                            "Input: audio #%d (%d bytes) amplitude min=%d max=%d rms=%d",
                            audio_packet_count,
                            len(data),
                            amp[0],
                            amp[1],
                            amp[2],
                        )
                    elif audio_packet_count % 50 == 0:
                        logger.debug("Input: %d audio packets received", audio_packet_count)
                    self._transition_state("LISTENING")
                    await self._adapter.send(data, mime_type="audio/pcm")
                case ControlInput(action="interrupt"):
                    await self.interrupt()
                case ControlInput(action="end_turn"):
                    await self._adapter.end_audio_stream()
                case ControlInput(action="close"):
                    await self.close()
                    break
        logger.debug("Input handler finished")

    async def _handle_output(self, transport: Transport) -> None:
        """Receive events from adapter and forward to transport, handling tool calls."""
        output_audio_count = 0
        try:
            async for chunk in self._adapter.receive():
                if self._closed:
                    break

                match chunk:
                    case LiveChunk(type="text", text=text) if text:
                        logger.debug("Output: text '%s'", text[:60])
                        if self._turn_start_time is None:
                            self._turn_start_time = time.perf_counter()
                            events.turn_started(self._session_id, self._turn_count + 1)
                        self._transition_state("SPEAKING")
                        self._turn_text_buffer.append(text)
                        await transport.send(TextDelta(text=text))
                    case LiveChunk(type="audio", audio=audio) if audio:
                        output_audio_count += 1
                        if output_audio_count == 1:
                            logger.debug("Output: first audio chunk (%d bytes)", len(audio))
                        if self._turn_start_time is None:
                            self._turn_start_time = time.perf_counter()
                            events.turn_started(self._session_id, self._turn_count + 1)
                        self._transition_state("SPEAKING")
                        await transport.send(AudioDelta(data=audio))
                    case LiveChunk(type="interrupted"):
                        await transport.send(StreamInterrupted(reason="user_interrupted"))
                    case LiveChunk(type="transcript", text=text) if text:
                        await transport.send(TextDelta(text=text))
                    case LiveChunk(type="input_transcript", text=text) if text:
                        await transport.send(TextDelta(text=text, role="user"))
                    case LiveChunk(type="turn_end"):
                        from relaykit.types import LiveResponse

                        self._tool_call_count = 0
                        self._turn_count += 1
                        if self._turn_start_time is not None:
                            turn_duration_ms = (time.perf_counter() - self._turn_start_time) * 1000
                            events.turn_ended(self._session_id, self._turn_count, turn_duration_ms)
                        self._turn_start_time = None
                        await self._run_output_guardrails()
                        self._turn_text_buffer.clear()
                        self._transition_state("IDLE")
                        await self._emit_turn_ended()
                        await transport.send(TurnComplete(response=LiveResponse()))

                        if self._max_turns is not None and self._turn_count >= self._max_turns:
                            await self.close()
                    case LiveChunk(type="tool_call", tool_calls=calls) if calls:
                        self._transition_state("TOOL_EXECUTING")
                        await self._handle_tool_calls(calls)
                    case LiveChunk(type="session_reconnecting"):
                        await transport.send(StreamInterrupted(reason="session_reconnecting"))
        except Exception as exc:
            logger.error("Output handler error: %s", exc, exc_info=True)
            raise
        logger.debug("Output handler finished")

    async def _handle_tool_calls(self, calls: tuple[Any, ...]) -> None:
        """Execute tool calls and send results back to the model."""
        from relaykit.types import ToolResponse

        tool_calls = [ToolCall(id=c.id, name=c.name, arguments=c.args) for c in calls]

        for tc in tool_calls:
            if self._active_hooks:
                await self._active_hooks.on_tool_start(tc.name, tc.arguments)
            await self._emit_tool_started(tc)

        # Check approval for tools that require it
        if self._approval_gate:
            tool_calls, denied_results = await self._check_tool_approvals(tool_calls)
        else:
            denied_results = []

        t0 = time.perf_counter()
        if tool_calls:
            results = await self._agent.tools.execute(
                tool_calls,
                context=self._tool_context,
                max_concurrency=self._agent.config.max_tool_concurrency,
            )
        else:
            results = []
        elapsed_ms = (time.perf_counter() - t0) * 1000

        all_results = denied_results + results

        for result in results:
            tc = next(c for c in tool_calls if c.id == result.call_id)
            if result.is_error:
                events.tool_called(
                    self._session_id, tc.name, elapsed_ms, success=False, error=result.output
                )
                if self._active_hooks:
                    await self._active_hooks.on_tool_error(tc.name, Exception(result.output))
                await self._emit_tool_failed(tc, result.output)
            else:
                events.tool_called(self._session_id, tc.name, elapsed_ms, success=True)
                if self._active_hooks:
                    await self._active_hooks.on_tool_end(tc.name, result.output)
                await self._emit_tool_completed(tc, result.output, elapsed_ms)

        tool_responses = [ToolResponse(call_id=r.call_id, result=r.output) for r in all_results]

        # Check for handoff sentinel in results
        from relaykit.handoff import is_handoff_result

        for result in results:
            if not result.is_error and is_handoff_result(result.output):
                self._pending_handoff = result.output
                await self.close()
                return

        # Check for delegation sentinel in results (does not close session)
        from relaykit.delegation import is_delegation_result, parse_delegation_result

        for i, result in enumerate(all_results):
            if not result.is_error and is_delegation_result(result.output):
                name, context = parse_delegation_result(result.output)
                await self._start_delegation(name, context)
                tool_responses[i] = ToolResponse(
                    call_id=result.call_id,
                    result=f"Delegation to '{name}' started. You will receive operational updates.",
                )

        await self._adapter.send_tool_response(tool_responses)
        self._tool_call_count += 1

        self._transition_state("THINKING")

        if self._tool_call_count > self._agent.config.max_tool_rounds:
            if self._agent.config.tool_limit_action == "close":
                logger.warning(
                    "Too many consecutive tool calls (%d), closing session",
                    self._tool_call_count,
                )
                await self.close()
            else:
                logger.warning(
                    "Too many consecutive tool calls (%d), continuing",
                    self._tool_call_count,
                )

    async def _run_input_guardrails(self, text: str) -> str | None:
        """Run input guardrails. Returns modified text or None if blocked."""
        guardrails = self._agent.input_guardrails
        if not guardrails:
            return text
        result = await run_guardrails(guardrails, text)
        if result.blocked:
            events.guardrail_triggered(self._session_id, "input", result.message)
            logger.info("Input blocked by guardrail: %s", result.message)
            return None
        if result.action == "modify" and result.modified_content is not None:
            return result.modified_content
        return text

    async def _run_output_guardrails(self) -> None:
        """Run output guardrails on accumulated turn text (observability/alerting)."""
        guardrails = self._agent.output_guardrails
        if not guardrails or not self._turn_text_buffer:
            return
        full_text = "".join(self._turn_text_buffer)
        result = await run_guardrails(guardrails, full_text)
        if result.blocked:
            events.guardrail_triggered(self._session_id, "output", result.message)
            logger.warning("Output guardrail triggered (post-stream): %s", result.message)
        elif result.action == "modify":
            events.guardrail_triggered(self._session_id, "output", result.message)

    async def _check_tool_approvals(
        self, tool_calls: list[ToolCall]
    ) -> tuple[list[ToolCall], list[Any]]:
        """Check approval for tools that require it. Returns (approved, denied_results)."""
        from relaykit.supervision.hitl import InputTimeoutError
        from relaykit.tools import ToolResult

        approved: list[ToolCall] = []
        denied_results: list[ToolResult] = []

        for tc in tool_calls:
            tool_def = self._agent.tools.get(tc.name)
            if tool_def is None or not tool_def.requires_approval:
                approved.append(tc)
                continue

            await self._emit_approval_requested(tc)
            self._transition_state("WAITING_FOR_INPUT")

            try:
                is_approved = await self._approval_gate.approve(
                    f"{tc.name}({tc.arguments})",
                    context={"tool_name": tc.name, "arguments": tc.arguments},
                    timeout=self._config.approval_timeout,
                )
            except InputTimeoutError:
                is_approved = self._config.approval_timeout_action == "proceed"

            await self._emit_approval_resolved(tc, is_approved)
            self._transition_state("TOOL_EXECUTING")

            if is_approved:
                approved.append(tc)
            else:
                denied_results.append(
                    ToolResult(
                        call_id=tc.id,
                        output="Tool execution denied by approval gate.",
                        is_error=True,
                    )
                )

        return approved, denied_results

    async def _emit_approval_requested(self, tc: ToolCall) -> None:
        if not self._event_bus:
            return
        from relaykit.supervision.events import ToolApprovalRequested

        await self._event_bus.emit(
            ToolApprovalRequested(
                source="session",
                tool_name=tc.name,
                call_id=tc.id,
                arguments=tc.arguments,
            )
        )

    async def _emit_approval_resolved(self, tc: ToolCall, approved: bool) -> None:
        if not self._event_bus:
            return
        from relaykit.supervision.events import ToolApprovalResolved

        await self._event_bus.emit(
            ToolApprovalResolved(
                source="session",
                tool_name=tc.name,
                call_id=tc.id,
                approved=approved,
            )
        )

    async def _disconnect(self) -> None:
        """Disconnect from the provider."""
        if self._adapter and self._connected:
            try:
                await self._adapter.disconnect()
            except Exception as exc:
                logger.debug("Disconnect error: %s", exc)
            finally:
                self._connected = False

    # --- Delegation lifecycle ---

    async def _start_delegation(self, backend_name: str, context: str) -> None:
        """Start a delegated execution as a background task."""
        from relaykit.delegation import DelegationHandle, DelegationState
        from relaykit.memory import OperationalMemory
        from relaykit.relay import SupervisionRelay
        from relaykit.supervision import CancellationToken, EventBus, InputManager, supervise

        backend = self._find_backend(backend_name)
        if backend is None:
            logger.warning("No backend found with name: %s", backend_name)
            return

        run_id = uuid.uuid4().hex
        bus = EventBus()
        input_mgr = InputManager(event_bus=bus)
        cancel_token = CancellationToken()
        memory = OperationalMemory()

        async def _inject_signal(signal: Any) -> None:
            memory.record(signal)
            if self._adapter and hasattr(self._adapter, "deliver_runtime_context"):
                rendered = f"[Runtime: {signal.summary}]"
                await self._adapter.deliver_runtime_context(rendered, transient=True)

        relay = SupervisionRelay(
            policy=backend.policy,
            event_bus=bus,
            inject=_inject_signal,
        )
        await relay.start(run_id=run_id)

        handle = DelegationHandle(
            backend_name=backend_name,
            run_id=run_id,
            state=DelegationState.RUNNING,
            relay=relay,
            event_bus=bus,
            input_manager=input_mgr,
            cancellation_token=cancel_token,
            operational_memory=memory,
        )

        async def _run_supervised() -> None:
            try:
                result = await supervise(
                    backend.adapter,
                    context,
                    event_bus=bus,
                    input_manager=input_mgr,
                    cancellation_token=cancel_token,
                    interrupt_timeout=backend.policy.interrupt_timeout,
                    run_id=run_id,
                )
                handle.state = DelegationState.COMPLETED
                handle.result = result
            except asyncio.CancelledError:
                handle.state = DelegationState.CANCELLED
            except Exception as exc:
                handle.state = DelegationState.FAILED
                logger.warning("Delegation '%s' failed: %s", backend_name, exc)
            finally:
                handle.completed_at = time.time()
                await relay.stop()

        task = asyncio.create_task(_run_supervised())
        handle.task = task

        def _on_cancel() -> None:
            task.cancel()

        cancel_token.on_cancel(_on_cancel)
        self._active_delegations[backend_name] = handle

    def _find_backend(self, name: str) -> Any:
        """Look up a declared DelegatedBackend by name."""
        for d in self._agent._delegations:
            if d.name == name:
                return d
        return None

    # --- Supervision helpers (no-ops when supervision=False) ---

    def _register_for_supervision(self) -> None:
        """Register this session in the global registry for external supervision."""
        if self._config.supervision:
            from relaykit.supervise import register_session

            register_session(self._session_id, self)

    def _unregister_from_supervision(self) -> None:
        """Remove this session from the global registry."""
        if self._config.supervision:
            from relaykit.supervise import unregister_session

            unregister_session(self._session_id)

    def _transition_state(self, _target: str) -> None:
        """No-op. State machine removed; kept for future supervision hook."""
        return

    async def _emit_session_started(self) -> None:
        if not self._event_bus:
            return
        from relaykit.supervision.events import SessionStarted

        await self._event_bus.emit(
            SessionStarted(
                source="session",
                model=self._agent.model,
                session_id=self._session_id,
            )
        )

    async def _emit_session_ended(self) -> None:
        if not self._event_bus:
            return
        from relaykit.supervision.events import SessionEnded

        await self._event_bus.emit(
            SessionEnded(
                source="session",
                session_id=self._session_id,
                reason="closed" if self._closed else "error",
            )
        )

    async def _emit_turn_ended(self) -> None:
        if not self._event_bus:
            return
        from relaykit.supervision.events import TurnEnded

        await self._event_bus.emit(TurnEnded(source="session", role="model"))

    async def _emit_tool_started(self, tc: ToolCall) -> None:
        if not self._event_bus:
            return
        from relaykit.supervision.events import ToolExecutionStarted

        await self._event_bus.emit(
            ToolExecutionStarted(
                source="session",
                tool_name=tc.name,
                arguments=tc.arguments,
                call_id=tc.id,
            )
        )

    async def _emit_tool_completed(self, tc: ToolCall, result: str, duration_ms: float) -> None:
        if not self._event_bus:
            return
        from relaykit.supervision.events import ToolExecutionCompleted

        await self._event_bus.emit(
            ToolExecutionCompleted(
                source="session",
                tool_name=tc.name,
                call_id=tc.id,
                result=result,
                duration_ms=duration_ms,
            )
        )

    async def _emit_tool_failed(self, tc: ToolCall, error: str) -> None:
        if not self._event_bus:
            return
        from relaykit.supervision.events import ToolExecutionFailed

        await self._event_bus.emit(
            ToolExecutionFailed(
                source="session",
                tool_name=tc.name,
                call_id=tc.id,
                error=error,
            )
        )

    @staticmethod
    def _audio_amplitude(data: bytes) -> tuple[int, int, int]:
        """Return (min, max, rms) of PCM16 audio for diagnostics."""
        if len(data) < 2:
            return (0, 0, 0)
        n_samples = len(data) // 2
        samples = struct.unpack(f"<{n_samples}h", data[: n_samples * 2])
        mn = min(samples)
        mx = max(samples)
        rms = int((sum(s * s for s in samples) / n_samples) ** 0.5)
        return (mn, mx, rms)
