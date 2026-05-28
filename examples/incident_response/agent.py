"""Incident response agent — LLM-driven ReAct graph with human-in-the-loop.

Uses Gemini 2.5 Flash to investigate a production outage by calling simulated
operational tools, then proposes a mitigation plan and pauses for human approval
via LangGraph interrupt().

Architecture:
  START -> investigate (LLM + tools loop) -> propose_mitigation -> approve -> execute -> END

Requires: langgraph>=0.3.0, langchain-google-genai.
Auth: Set GOOGLE_API_KEY, or set GOOGLE_CLOUD_PROJECT + GOOGLE_VERTEX_LOCATION for Vertex AI.
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from langchain_core.messages import AnyMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt
from typing_extensions import TypedDict

from tools import (
    check_dependencies,
    check_deployments,
    check_metrics,
    page_oncall,
    query_logs,
    rollback_deployment,
    run_query,
    scale_service,
    toggle_feature_flag,
)

class IncidentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    alert: str
    mitigation_plan: str
    status: str


investigation_tools = [check_metrics, query_logs, check_deployments, check_dependencies, run_query]
mitigation_tools = [scale_service, rollback_deployment, toggle_feature_flag, page_oncall]

_llm_cache: dict[str, Any] = {}


def _get_llm() -> ChatGoogleGenerativeAI:
    if "base" not in _llm_cache:
        kwargs: dict[str, Any] = {"model": "gemini-2.5-flash", "temperature": 0.3}
        if os.environ.get("GOOGLE_CLOUD_PROJECT"):
            kwargs["vertexai"] = True
            kwargs["project"] = os.environ["GOOGLE_CLOUD_PROJECT"]
            location = os.environ.get("GOOGLE_VERTEX_LOCATION", "us-central1")
            kwargs["location"] = location
        _llm_cache["base"] = ChatGoogleGenerativeAI(**kwargs)
    return _llm_cache["base"]


def _get_investigation_llm() -> Any:
    if "investigation" not in _llm_cache:
        _llm_cache["investigation"] = _get_llm().bind_tools(investigation_tools)
    return _llm_cache["investigation"]


def _get_mitigation_llm() -> Any:
    if "mitigation" not in _llm_cache:
        _llm_cache["mitigation"] = _get_llm().bind_tools(mitigation_tools)
    return _llm_cache["mitigation"]


INVESTIGATION_PROMPT = SystemMessage(
    content=(
        "You are an SRE investigating a production incident. Use the available tools to "
        "gather evidence, correlate signals, and identify root cause. Be systematic: check "
        "metrics, logs, deployments, and dependencies. Once you have enough evidence, stop "
        "calling tools and summarize your findings."
    )
)

MITIGATION_PROMPT = SystemMessage(
    content=(
        "Based on your investigation, propose a mitigation plan. Include:\n"
        "1) Root cause hypothesis\n"
        "2) Proposed action (specific tool calls you would make)\n"
        "3) Risk/impact assessment\n"
        "4) Estimated time to resolution\n\n"
        "Respond with a clear, structured plan. Do NOT call any tools."
    )
)

EXECUTION_PROMPT = SystemMessage(
    content=(
        "Execute the approved mitigation plan using the available tools. "
        "Call the necessary tools to implement the mitigation, then confirm completion."
    )
)

def investigate(state: IncidentState) -> dict[str, Any]:
    """Invoke the LLM with investigation tools to gather evidence."""
    messages = state["messages"]
    if not messages or messages[0].type != "system":
        alert_msg = f"ALERT: {state['alert']}\n\nInvestigate this incident."
        messages = [INVESTIGATION_PROMPT, {"role": "user", "content": alert_msg}] + messages[1:]
    response = _get_investigation_llm().invoke(messages)
    return {"messages": [response], "status": "investigating"}


def propose_mitigation(state: IncidentState) -> dict[str, Any]:
    """Ask the LLM to propose a mitigation plan based on investigation findings."""
    messages = state["messages"] + [MITIGATION_PROMPT]
    response = _get_llm().invoke(messages)
    plan = response.content if isinstance(response.content, str) else str(response.content)
    return {
        "messages": [response],
        "mitigation_plan": plan,
        "status": "awaiting_approval",
    }


def approve(state: IncidentState) -> dict[str, Any]:
    """Pause for human approval via interrupt()."""
    decision = interrupt(
        {
            "type": "mitigation_approval",
            "plan": state["mitigation_plan"],
            "options": ["approve", "deny", "<feedback text>"],
        }
    )

    if decision == "approve":
        return {"status": "mitigating"}
    if decision == "deny":
        return {"status": "denied"}
    # Any other text is feedback — inject it and loop back to investigation
    feedback_msg = {"role": "user", "content": f"OPERATOR FEEDBACK: {decision}"}
    return {"messages": [feedback_msg], "status": "investigating"}


def execute(state: IncidentState) -> dict[str, Any]:
    """Invoke the LLM with mitigation tools to execute the approved plan."""
    exec_msg = {
        "role": "user",
        "content": (
            f"The following mitigation plan has been APPROVED. Execute it now:\n\n"
            f"{state['mitigation_plan']}"
        ),
    }
    messages = state["messages"] + [EXECUTION_PROMPT, exec_msg]
    response = _get_mitigation_llm().invoke(messages)
    return {"messages": [response], "status": "resolved"}


def after_investigate(state: IncidentState) -> str:
    """Route after investigate: tools if tool_calls present, else propose."""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "propose_mitigation"


def after_approve(state: IncidentState) -> str:
    """Route after approve: end if denied, investigate if feedback, else execute."""
    if state["status"] == "denied":
        return "end"
    if state["status"] == "investigating":
        return "investigate"
    return "execute"


builder = StateGraph(IncidentState)

builder.add_node("investigate", investigate)
builder.add_node("tools", ToolNode(investigation_tools))
builder.add_node("propose_mitigation", propose_mitigation)
builder.add_node("approve", approve)
builder.add_node("execute", execute)

builder.add_edge(START, "investigate")
builder.add_conditional_edges(
    "investigate",
    after_investigate,
    {
        "tools": "tools",
        "propose_mitigation": "propose_mitigation",
    },
)
builder.add_edge("tools", "investigate")
builder.add_edge("propose_mitigation", "approve")
builder.add_conditional_edges(
    "approve",
    after_approve,
    {
        "end": END,
        "investigate": "investigate",
        "execute": "execute",
    },
)
builder.add_edge("execute", END)

graph = builder.compile(checkpointer=MemorySaver())

INITIAL_STATE: dict[str, Any] = {
    "messages": [],
    "alert": "Elevated 5xx error rate on checkout-service (12.4%, baseline 0.3%). Started 14:32 UTC.",
    "mitigation_plan": "",
    "status": "new",
}
