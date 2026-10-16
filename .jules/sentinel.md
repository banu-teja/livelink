
## 2024-05-24 - Cross-Site WebSocket Hijacking (CSWSH) in Custom WebSocket Server
**Vulnerability:** The custom WebSocket server implementation in `src/livelink/serve.py` using `websockets` library handled `process_request` without explicitly validating the `Origin` header during the HTTP handshake for WebSocket connections.
**Learning:** Even when using well-established libraries like `websockets`, if you implement custom routing or connection handling logic (like `process_request` intercepting the handshake), you are responsible for implementing origin checks. The default behavior might not block requests from malicious origins.
**Prevention:** Always validate the `Origin` header against the expected host (`Host` or `X-Forwarded-Host` headers) during the WebSocket handshake when CORS is not explicitly enabled. Return an early 403 Forbidden response if they don't match.
