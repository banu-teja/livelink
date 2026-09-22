
## 2024-10-24 - Cross-Site WebSocket Hijacking (CSWSH) in serve.py
**Vulnerability:** The default local WebSocket server (`serve.py`) allowed connections from any browser origin when `cors=False`.
**Learning:** `websockets` library relies on custom `process_request` logic or explicit `origins` configuration to validate origins. Returning `None` from `process_request` without checking the `Origin` header bypasses CSRF/CSWSH protection, allowing malicious web pages to interact with local agents.
**Prevention:** Always validate the `Origin` header against the expected `Host` header (or permitted origins list) in custom `process_request` implementations for WebSockets.
