## 2025-03-02 - Cross-Site WebSocket Hijacking (CSWSH)
**Vulnerability:** The `agent.serve()` WebSocket handler did not validate the `Origin` header during the HTTP handshake for WebSocket connections.
**Learning:** Because WebSocket endpoints do not inherently protect against cross-site requests, omitting origin validation allows an attacker to hijack a session or interact with the agent from an unauthorized origin by forcing a user to visit an attacker-controlled site.
**Prevention:** Always validate the `Origin` header against the expected `Host` or `X-Forwarded-Host` during the HTTP WebSocket upgrade request unless Cross-Origin Resource Sharing (CORS) is explicitly enabled. Reject mismatched connections with a 403 Forbidden.
