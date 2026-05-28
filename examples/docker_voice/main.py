"""Docker Voice Agent — zero-config container entrypoint.

Run via docker-compose:
    docker-compose up

Then open http://localhost:8000 in a browser.
"""

from relaykit import LiveAgent

agent = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions="You are a helpful voice assistant. Keep responses brief.",
)
agent.serve(host="0.0.0.0", port=8000)
