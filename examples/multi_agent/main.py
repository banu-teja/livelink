"""Multi-agent handoff: router dispatches to specialist agents.

Run: uv run python examples/multi_agent/main.py
Then open http://localhost:8003 in a browser.

Say something like "I have a billing question" or "My internet is not working"
to trigger a handoff to the appropriate specialist.
"""

from relaykit import Handoff, LiveAgent

billing = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions=(
        "You are a billing specialist. Help with invoices, payments, "
        "refunds, and subscription changes. Be precise with numbers."
    ),
    voice="Kore",
)

technical = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions=(
        "You are a technical support specialist. Help with connectivity, "
        "hardware issues, software bugs, and troubleshooting steps."
    ),
    voice="Charon",
)

router = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions=(
        "You are a support router. Greet the user and ask how you can help. "
        "Transfer to billing for payment/invoice questions, "
        "or to technical for connectivity/hardware/software issues."
    ),
    voice="Puck",
    handoffs=[
        Handoff(
            target=billing,
            tool_name="transfer_to_billing",
            tool_description="Transfer to billing for payment and invoice questions.",
        ),
        Handoff(
            target=technical,
            tool_name="transfer_to_technical",
            tool_description="Transfer to technical support for hardware/software issues.",
        ),
    ],
)
router.serve(port=8003)
