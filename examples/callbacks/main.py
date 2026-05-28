"""Runner with observation callbacks for production monitoring.

Run: uv run python examples/callbacks/main.py
Then open http://localhost:8005 in a browser.

Demonstrates Runner.run() with callbacks for tool observability,
turn tracking, and error handling.
"""

import asyncio
import logging

from relaykit import LiveAgent, Runner, WebSocketTransport

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

agent = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions="You are a helpful assistant. When asked about weather, use the get_weather tool.",
    voice="Puck",
)


@agent.tool
async def get_weather(city: str) -> str:
    """Get current weather for a city.

    Args:
        city: City name to look up
    """
    return f"Weather in {city}: 72F, partly cloudy."


async def main() -> None:
    try:
        from websockets.asyncio.server import serve as ws_serve
    except ImportError:
        raise ImportError("Install websockets: pip install relaykit[serve]") from None

    async def handle_connection(connection) -> None:
        transport = WebSocketTransport(connection)
        result = await Runner.run(
            agent,
            transport,
            on_turn_start=lambda role: logger.info("[turn] %s started", role),
            on_turn_end=lambda turn: logger.info("[turn] ended: %s", turn),
            on_tool_start=lambda name, args: logger.info("[tool] %s(%s)", name, args),
            on_tool_end=lambda name, res: logger.info("[tool] %s -> %s", name, res),
            on_error=lambda err: logger.error("[error] %s", err),
        )
        logger.info("[done] %d turns, reason=%s", result.turn_count, result.stopped_reason)

    print("RelayKit agent -> http://localhost:8005")
    async with ws_serve(handle_connection, "localhost", 8005):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
