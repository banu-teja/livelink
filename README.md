# RelayKit

The supervised runtime for voice AI agents.

5 lines to a working voice agent. Add tools in +3. Add guardrails in +5. Grow to multi-agent without rewriting.

## Install

```bash
pip install livelink[gemini,serve]   # Gemini Live
pip install livelink[openai,serve]   # OpenAI Realtime
pip install livelink[all]            # All providers + serve
```

Requires Python 3.10+.

## Quickstart

Get a [Google AI API key](https://aistudio.google.com/apikey), then:

```bash
export GOOGLE_API_KEY=your-key-here
```

```python
from livelink import LiveAgent

agent = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions="You are a helpful voice assistant.",
)
agent.serve()
```

Open http://localhost:8000. Talk to your agent.

## Add a Tool (+3 lines)

```python
from livelink import LiveAgent

agent = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions="You help with weather questions.",
)

@agent.tool
async def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"72°F and sunny in {city}"

agent.serve()
```

Tool schemas are inferred automatically from type hints and docstrings.

## Add Guardrails (+5 lines)

```python
from livelink import LiveAgent, input_guardrail, GuardrailResult

@input_guardrail
async def block_pii(content: str) -> GuardrailResult:
    if "@" in content or "SSN" in content:
        return GuardrailResult(action="block", message="PII detected")
    return GuardrailResult(action="pass")

agent = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions="You are a helpful voice assistant.",
    input_guardrails=[block_pii],
)
agent.serve()
```

Guardrails run at every input/output boundary. Chain multiple, modify content, or block outright.

## Multi-Agent Handoffs (+8 lines)

```python
from livelink import LiveAgent, Handoff

billing = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions="You are a billing specialist.",
)

agent = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions="You are a support router. Transfer billing questions.",
    handoffs=[Handoff(target=billing, tool_name="transfer_to_billing")],
)
agent.serve()
```

The transport stays open. Conversation history accumulates across swaps.

## What's Included

**Providers**
- Gemini Live (Google GenAI SDK)
- OpenAI Realtime API
- One interface for both — swap `model=` to switch

**Runtime**
- `agent.serve()` — zero-config WebSocket server + browser UI
- `Runner.run(agent, transport)` — structured lifecycle with callbacks
- `agent.session().run(transport)` — full manual control
- All three use the same underlying session — no rewrite cliffs

**Supervision**
- Observable tool calls, audio events, and reasoning steps via EventBus
- Human-in-the-loop (HITL) input requests with priority, timeout, cancellation
- Background task management with cancellation support
- Conversation state machine (idle → active → interrupted → complete)

**Agent patterns**
- `@agent.tool` — automatic JSON schema from type hints + docstrings
- `@input_guardrail` / `@output_guardrail` — content validation at boundaries
- `Handoff` — control transfer between agents (transport stays open)
- `agent.as_tool()` — delegation pattern (sub-agent runs as a tool call)

**LangGraph integration**
```bash
pip install livelink[langchain]
```
Run any LangGraph graph as a voice agent with full interrupt/resume support.

## Docker

```bash
export GOOGLE_API_KEY=your-key
docker-compose up
# Open http://localhost:8000
```

## Architecture

One runtime path, progressively revealed:

```
agent.serve()                         # 5 lines — zero config
Runner.run(agent, transport, on_*=…)  # 15 lines — callbacks + lifecycle
agent.session(config=…).run(transport)# 30+ lines — full control
```

`LiveAgent` is pure config. `RealtimeSession` is the runtime. `Runner` manages the lifecycle between them. Adapters translate provider-specific protocols — your code never sees the difference.

## Examples

See [`examples/`](examples/) for runnable demos:

- `minimal_voice/` — simplest possible agent
- `pizza_order/` — tool use with structured state
- `supervised_agent/` — HITL approvals and supervisor injection
- `escalation_handler/` — multi-step investigation with graduated autonomy
- `multi_agent/` — handoffs and delegation
- `guardrails/` — input/output content filtering
- `incident_response/` — LangGraph ReAct agent with voice interface

## License

MIT
