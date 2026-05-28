"""Agent with input/output guardrails for content safety.

Run: uv run python examples/guardrails/main.py
Then open http://localhost:8004 in a browser.

Try mentioning "social security number" or "credit card" to trigger the input guardrail.
"""

from relaykit import GuardrailResult, LiveAgent, input_guardrail, output_guardrail

PII_KEYWORDS = ["ssn", "social security", "credit card", "card number"]


@input_guardrail
async def block_pii(content: str) -> GuardrailResult:
    """Block messages that appear to contain PII."""
    if any(keyword in content.lower() for keyword in PII_KEYWORDS):
        return GuardrailResult(action="block", message="PII detected in input")
    return GuardrailResult(action="pass")


@output_guardrail
async def redact_emails(content: str) -> GuardrailResult:
    """Redact email addresses from model output."""
    import re

    redacted = re.sub(r"\b[\w.-]+@[\w.-]+\.\w+\b", "[EMAIL REDACTED]", content)
    if redacted != content:
        return GuardrailResult(action="modify", modified_content=redacted)
    return GuardrailResult(action="pass")


agent = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions="You are a helpful assistant. Never ask for or repeat sensitive personal data.",
    voice="Puck",
    input_guardrails=[block_pii],
    output_guardrails=[redact_emails],
)
agent.serve(port=8004)
