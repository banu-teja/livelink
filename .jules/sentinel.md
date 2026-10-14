## 2024-10-15 - [CSWSH Prevention in Custom WebSocket Handler]
**Vulnerability:** The application used a custom `process_request` handler for `websockets` that didn't validate the `Origin` against the `Host` header, exposing the app to Cross-Site WebSocket Hijacking (CSWSH) if a malicious site tricked an authenticated user's browser into connecting.
**Learning:** When using lower-level WebSocket libraries like `websockets` and manually handling HTTP handshakes, built-in CORS protections often don't apply automatically to the WebSocket upgrade request itself.
**Prevention:** Always explicitly validate the `Origin` header against the `Host` (and `X-Forwarded-Host` for proxies) in the initial WebSocket HTTP handshake handler when CORS is meant to be disabled or restricted.
