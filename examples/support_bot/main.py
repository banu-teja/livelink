"""IT support bot that creates tickets via tool calling.

Run: uv run python examples/support_bot/main.py
Then open http://localhost:8002 in a browser.
"""

import logging

from livelink import LiveAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

agent = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions=(
        "You are a frontline IT support agent. Your voice is warm and professional. "
        "Greet the user, ask for their name, and what issue they are facing. "
        "Once you have both pieces of information, use the log_ticket tool. "
        "Then tell them their ticket number. Keep responses concise."
    ),
    voice="Aoede",
)


@agent.tool
async def log_ticket(name: str, issue: str) -> str:
    """Log a support ticket after collecting the user's name and issue.

    Args:
        name: The user's name
        issue: Description of their IT issue
    """
    logger.info("TICKET CREATED: name=%s issue=%s", name, issue)
    return '{"status": "success", "ticket_id": "TCK-9981"}'


agent.serve(port=8002)
