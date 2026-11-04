## 2024-05-04 - WebSocket Origin Validation (CSWSH)
**Vulnerability:** The `agent.serve()` WebSocket server doesn't validate the `Origin` header during the handshake when CORS is disabled.
**Learning:** This is a custom WebSocket server utilizing the `websockets` library. The custom `process_request` allows all cross-origin requests which exposes the system to Cross-Site WebSocket Hijacking (CSWSH). If CORS is false, origin check should be enforced.
**Prevention:** Always validate `Origin` header against expected host in custom websocket implementations. Make sure parsing handles IPv6 gracefully.
