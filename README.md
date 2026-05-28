# RelayKit

The supervised runtime for voice AI agents.

5 lines to a working voice agent. Add tools in +3. Add guardrails in +5. Grow to multi-agent without rewriting.

## The 3-Minute Experience

Prerequisites: Python 3.10+, a [Google AI API key](https://aistudio.google.com/apikey).

```bash
pip install relaykit[gemini,serve]
export GOOGLE_API_KEY=your-key-here
```

```python
from relaykit import LiveAgent

agent = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions="You are a helpful voice assistant.",
)
agent.serve()
```

Run it. Open http://localhost:8000. Talk to your agent.

## Add a Tool (+3 lines)

```python
from relaykit import LiveAgent

agent = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions="You help with weather questions.",
)

@agent.tool
async def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"72F and sunny in {city}"

agent.serve()
```

## Add Guardrails (+5 lines)

```python
from relaykit import LiveAgent, input_guardrail, GuardrailResult

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

## Multi-Agent Handoffs (+8 lines)

```python
from relaykit import LiveAgent, Handoff

billing = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions="You are a billing specialist. Help with invoices and payments.",
)

agent = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions="You are a support router. Transfer billing questions.",
    handoffs=[Handoff(target=billing, tool_name="transfer_to_billing")],
)
agent.serve()
```

## What Makes This Different

| | RelayKit | LiveKit Agents | Pipecat | OpenAI Agents SDK |
|---|---|---|---|---|
| Time to first voice | 3 min | 15-30 min | 10-20 min | N/A (text only) |
| Built-in supervision | Yes | No | No | No |
| Provider agnostic | Yes | Yes | Yes | No |
| Progressive complexity | Yes | No | No | Yes |

## Install

```bash
pip install relaykit[gemini,serve]   # Gemini Live (recommended)
pip install relaykit[openai,serve]   # OpenAI Realtime
pip install relaykit[all]            # All providers + serve
```

## Quick Start with Docker

```bash
export GOOGLE_API_KEY=your-key
docker-compose up
# Open http://localhost:8000
```

## Architecture

RelayKit has one runtime path with progressive complexity:

1. `agent.serve()` -- zero-config server with browser UI (5 lines)
2. `Runner.run(agent, transport)` -- structured lifecycle with callbacks (15 lines)
3. `agent.session().run(transport)` -- full manual control (30 lines)

All three use the same underlying `RealtimeSession`. No rewrite cliffs. Start simple, add supervision and multi-agent when you need it.

## Documentation

See `examples/` for runnable demos. Full docs site coming soon.

## License

MIT
