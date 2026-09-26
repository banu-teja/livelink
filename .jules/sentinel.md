## 2024-10-25 - [Fix CSWSH and add Security Headers]
**Vulnerability:** Unauthenticated Cross-Site WebSocket Hijacking (CSWSH) potential and missing HTTP security headers on websocket serving endpoints.
**Learning:** The websocket server setup was lacking Origin validation on the process_request hook when cors is false.
**Prevention:** Ensure Origin checks are enforced against the Host during the initial HTTP handshake for websocket upgrades when CORS is not explicitly enabled. Add standard security headers (X-Content-Type-Options, X-Frame-Options) to all HTTP responses.
