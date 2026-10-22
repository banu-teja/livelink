## 2024-05-24 - CSWSH Prevention in Custom WebSocket Handshake
**Vulnerability:** Cross-Site WebSocket Hijacking (CSWSH) could allow malicious websites to establish WebSocket connections to the local/authenticated server because WebSockets do not strictly enforce the Same-Origin Policy by default.
**Learning:** The project relies on the standard `websockets` package which delegates handshake verification to the user via the `process_request` hook. Without an explicit origin check, the application is vulnerable.
**Prevention:** Always validate the `Origin` header against `Host` or `X-Forwarded-Host` during the `process_request` hook when handling WebSockets, ensuring connections originating from untrusted domains are rejected with a 403 Forbidden.
