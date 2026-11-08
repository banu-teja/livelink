## 2024-05-15 - [CSWSH Prevention]
**Vulnerability:** Missing CSWSH (Cross-Site WebSocket Hijacking) protection. The WebSocket server did not validate the `Origin` header against the `Host` header.
**Learning:** The project uses the `websockets` library which handles connections directly. To prevent CSWSH, custom validation logic is needed inside `process_request`, ensuring it fails closed on exceptions. Also, need to carefully handle bracketed IPv6 hosts as `urlparse().hostname` drops brackets.
**Prevention:** Enforce Origin validation during the WebSocket handshake when CORS is disabled.
