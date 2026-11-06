## 2024-05-15 - [CSWSH missing validation]
**Vulnerability:** The Custom WebSocket server built over the `websockets` library currently lacks Cross-Site WebSocket Hijacking (CSWSH) protection. It accepts connections unconditionally and does not validate the `Origin` header against the `Host` or `X-Forwarded-Host` headers.
**Learning:** Custom WebSocket implementations using `websockets` do not automatically provide CSWSH protection unless explicitly handled in `process_request` via rejecting cross-origin requests unless CORS is explicitly enabled.
**Prevention:** Implement `process_request` origin checks in custom WebSocket wrappers.
