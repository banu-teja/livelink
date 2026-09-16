## 2026-09-16 - Prevent Cross-Site WebSocket Hijacking in serve.py
**Vulnerability:** The local WebSocket server (`agent.serve()`) lacked `Origin` header validation and accepted connections from any origin. If a user browsed a malicious website, that site could open a WebSocket connection to `localhost:8000` and hijack the LiveLink agent, executing tools or intercepting streams.
**Learning:** In local development servers or internal WebSocket services, it's crucial to explicitly validate the `Origin` against the allowed host to prevent CSWSH.
**Prevention:** Always validate `Origin` against `Host` if CORS is not explicitly enabled. Add standard security headers (`Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`) even to internal or minimal HTTP endpoints.
