## 2025-02-14 - Prevent Cross-Site WebSocket Hijacking (CSWSH)
**Vulnerability:** The custom `serve.py` WebSocket handler accepted all incoming browser WebSocket connections without verifying the `Origin` header.
**Learning:** WebSockets bypass browser Same-Origin Policy. A custom ASGI/WebSocket server implementation must explicitly validate `Origin` against `Host` to prevent malicious sites from silently connecting on the user's behalf.
**Prevention:** Explicitly parse and match the Origin header to the requested Host/X-Forwarded-Host if CORS is not enabled. Return 403 on mismatch. Implement a fail-closed strategy if Origin parsing fails. Handle IPv6 bracket hostnames carefully as standard libraries often strip them.
