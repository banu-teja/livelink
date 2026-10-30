## 2024-05-24 - CSWSH Vulnerability in WebSocket Server
**Vulnerability:** The custom WebSocket server implementation (`process_request` in `serve.py`) does not validate the `Origin` header during the HTTP handshake, leading to potential Cross-Site WebSocket Hijacking (CSWSH) when `cors` is disabled.
**Learning:** When directly managing `process_request` hooks in Python `websockets` library to serve custom HTTP endpoints (like UI or health checks), the default origin validation behavior of the library may be bypassed or insufficient. We must manually validate `Origin` against `Host` or `X-Forwarded-Host`.
**Prevention:** Always implement explicit `Origin` vs `Host` validation in custom WebSocket handshake hooks unless CORS is explicitly enabled.
