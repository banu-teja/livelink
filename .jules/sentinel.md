## 2025-02-18 - [CSWSH] Missing Origin Validation in WebSocket Handshake
**Vulnerability:** The custom `process_request` in `livelink/serve.py` did not validate the `Origin` header against the requested Host, allowing Cross-Site WebSocket Hijacking (CSWSH).
**Learning:** When using the `websockets` library and providing a custom `process_request` handler, standard library validations are bypassed. The handler is solely responsible for verifying the `Origin` header.
**Prevention:** Always parse and validate `request.headers.get("Origin")` against `Host` or `X-Forwarded-Host` during the WebSocket HTTP handshake in custom handlers.
