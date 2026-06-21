"""LangGraphAdapter: bridges LangGraph astream_events(v3) to AdapterEvent protocol."""

from __future__ import annotations

import time
from typing import Any, AsyncIterator

try:
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.types import Command
except ImportError as e:
    raise ImportError(
        "LangGraphAdapter requires langgraph>=0.3.0: pip install livelink[langchain]"
    ) from e

from livelink.supervision.adapter import (
    AdapterEvent,
    InterruptRequestedEvent,
    LifecycleCompletedEvent,
    LifecycleStartedEvent,
    StepStartedEvent,
    TokenDeltaEvent,
    ToolCompletedEvent,
    ToolFailedEvent,
    ToolStartedEvent,
)


# ---------------------------------------------------------------------------
# Protocol isolation helpers
# ---------------------------------------------------------------------------


def _extract_method(event: dict) -> str:
    """Extract event method from LangGraph v3 protocol event dict."""
    return event.get("method", "") if isinstance(event, dict) else ""


def _extract_data(event: dict) -> dict:
    """Extract data dict from LangGraph v3 protocol event params."""
    if not isinstance(event, dict):
        return {}
    params = event.get("params", {})
    if isinstance(params, dict):
        data = params.get("data", {})
        return data if isinstance(data, dict) else {}
    return {}


def _extract_namespace(event: dict) -> list[str]:
    """Extract namespace list from LangGraph v3 protocol event params."""
    if not isinstance(event, dict):
        return []
    params = event.get("params", {})
    if isinstance(params, dict):
        ns = params.get("namespace", [])
        return ns if isinstance(ns, list) else []
    return []


# ---------------------------------------------------------------------------
# LangGraphAdapter
# ---------------------------------------------------------------------------


class LangGraphAdapter:
    """ExecutionAdapter implementation wrapping a compiled LangGraph state graph."""

    ADAPTER_VERSION = "1"
    SOURCE = "langgraph_v3"
    MIN_LANGGRAPH_VERSION = "0.3.0"

    def __init__(self, graph: CompiledStateGraph, *, config: dict[str, Any] | None = None) -> None:
        self._graph = graph
        self._config = config or {}
        self._cancelled = False

    async def start(self, input: Any) -> AsyncIterator[AdapterEvent]:
        self._cancelled = False
        async for event in self._consume_stream(input):
            yield event

    async def resume(self, value: Any) -> AsyncIterator[AdapterEvent]:
        self._cancelled = False
        async for event in self._consume_stream(Command(resume=value)):
            yield event

    async def cancel(self) -> None:
        self._cancelled = True

    async def _consume_stream(self, input: Any) -> AsyncIterator[AdapterEvent]:
        start_time = time.monotonic()
        step_index = 0
        interrupted = False

        yield LifecycleStartedEvent(input_summary=str(input)[:200])

        stream = await self._graph.astream_events(input, config=self._config, version="v3")

        async for event in stream:
            if self._cancelled:
                return

            # Detect interrupts from event params (v3 protocol)
            params = event.get("params", {}) if isinstance(event, dict) else {}
            interrupts = params.get("interrupts", ()) if isinstance(params, dict) else ()
            if interrupts:
                for intr in interrupts:
                    intr_id = (
                        intr.get("id", "unknown")
                        if isinstance(intr, dict)
                        else getattr(intr, "id", "unknown")
                    )
                    intr_payload = (
                        intr.get("value", None)
                        if isinstance(intr, dict)
                        else getattr(intr, "value", None)
                    )
                    yield InterruptRequestedEvent(
                        interrupt_id=intr_id,
                        payload=intr_payload,
                        step_name="interrupt",
                    )
                interrupted = True
                return

            method = _extract_method(event)
            data = _extract_data(event)
            namespace = _extract_namespace(event)

            if method == "lifecycle" and data.get("status") == "running" and namespace:
                yield StepStartedEvent(step_name="/".join(namespace), step_index=step_index)
                step_index += 1

            elif method == "tools":
                tool_type = data.get("type", "")
                tool_name = data.get("name", "unknown")
                call_id = data.get("call_id", "")

                if tool_type == "start":
                    yield ToolStartedEvent(
                        tool_name=tool_name,
                        call_id=call_id,
                        arguments_summary=str(data.get("arguments", ""))[:200],
                    )
                elif tool_type == "complete":
                    yield ToolCompletedEvent(
                        tool_name=tool_name,
                        call_id=call_id,
                        result_summary=str(data.get("result", ""))[:200],
                        duration_ms=data.get("duration_ms", 0.0),
                    )
                elif tool_type == "error":
                    yield ToolFailedEvent(
                        tool_name=tool_name,
                        call_id=call_id,
                        error=str(data.get("error", "unknown error")),
                    )

            elif method == "messages" and data.get("type") == "content-block-delta":
                content = data.get("content", "")
                step_name = "/".join(namespace) if namespace else "root"
                yield TokenDeltaEvent(content=content, step_name=step_name)

        if not interrupted:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            output = await stream.output()
            yield LifecycleCompletedEvent(
                output_summary=str(output)[:200] if output else "",
                duration_ms=duration_ms,
            )
