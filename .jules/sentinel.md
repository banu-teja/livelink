## 2024-10-18 - Cross-Site WebSocket Hijacking Protection
**Vulnerability:** The application was vulnerable to Cross-Site WebSocket Hijacking (CSWSH) because it did not validate the `Origin` header when upgrading the HTTP connection to a WebSocket in `agent.serve()`.
**Learning:** A custom implementation of process_request in the websockets library requires explicit origin validation. Relying on default configuration when custom handling is used can expose the service to unauthorized requests from any origin.
**Prevention:** Always validate the `Origin` header against an expected host (like `Host` or `X-Forwarded-Host`) when `cors` is disabled during the WebSocket upgrade handshake. Reject mismatched origins with a 403 Forbidden.
