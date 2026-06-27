## 2025-02-17 - Prevent Cross-Site WebSocket Hijacking (CSWSH)
**Vulnerability:** The default implementation of `serve.py` passed no origins configuration to `websockets.asyncio.server.serve`, which allows any website to establish a WebSocket connection if the user is running the agent locally. A malicious site could silently connect to the agent running on `localhost:8000` and utilize the AI/execute tools.
**Learning:** `websockets` does not restrict origins by default to allow flexibility, but this means an application providing a local service using WebSockets must explicitly set an origin policy.
**Prevention:** Always restrict WebSocket origins (e.g. `localhost` and `127.0.0.1`) when exposing a local development server or provide a specific `--cors` flag to override.
