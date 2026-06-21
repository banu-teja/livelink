"""Pizza ordering bot with tool calling.

Run: uv run python examples/pizza_order/main.py
Then open http://localhost:8001 in a browser.
"""

import logging

from livelink import LiveAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

agent = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions=(
        "You are a friendly pizza shop assistant at Mario's Pizza. "
        "Your job is to take the user's pizza order. Collect: "
        "1) Size (small, medium, large) "
        "2) Topping (pepperoni, margherita, mushroom, etc.) "
        "3) Crust type (thin, thick, stuffed) "
        "Once you have all three details AND the user confirms, "
        "call the place_order tool. Never assume details. "
        "Keep responses short and conversational. Start by greeting."
    ),
    voice="Puck",
)


@agent.tool
async def place_order(size: str, topping: str, crust: str) -> str:
    """Place a pizza order after collecting all details.

    Args:
        size: Pizza size (small, medium, large)
        topping: Pizza topping choice
        crust: Crust type (thin, thick, stuffed)
    """
    logger.info("ORDER PLACED: %s %s on %s crust", size, topping, crust)
    return f"Order confirmed: {size} {topping} on {crust} crust. Ready in 15 minutes!"


agent.serve(port=8001)
