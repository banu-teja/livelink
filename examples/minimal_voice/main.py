"""Minimal voice agent. Run: uv run python examples/minimal_voice/main.py"""

from livelink import LiveAgent

agent = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions="You are a friendly assistant. Keep responses short and natural.",
    voice="Puck",
)
agent.serve()
