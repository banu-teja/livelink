## 2024-05-15 - Fix Cross-Site WebSocket Hijacking (CSWSH) in Runtime Server
**Vulnerability:** The internal WebSocket server did not validate the `Origin` header against the `Host` header. This allowed malicious sites loaded in the user's browser to connect to the locally running `livelink` agent via `ws://127.0.0.1:8000`.
**Learning:** Custom WebSocket server implementations using `websockets.asyncio.server.serve` must manually validate origins in their `process_request` hook, as the library does not enforce origin matching by default unless explicitly configured or checked.
**Prevention:** Always compare `Origin` vs `Host` headers in `process_request` unless CORS is explicitly intended and securely configured. Return HTTP 403 when they do not match.
