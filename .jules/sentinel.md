## Sentinel Journal

## 2026-10-26 - [Critical] Cross-Site WebSocket Hijacking (CSWSH) in serve.py
**Vulnerability:** The built-in WebSocket server runtime (`agent.serve()`) lacked origin validation on connection upgrades. By default, it allowed any origin to connect, which enabled Cross-Site WebSocket Hijacking (CSWSH). A malicious site could instruct a victim's browser to open a WebSocket connection to the local/deployed agent on the victim's behalf, bypassing Same-Origin Policy (SOP).
**Learning:** Custom WebSocket HTTP handshakes using the `websockets` library (via `process_request`) do not enforce SOP by default. Because WebSockets don't use CORS headers in the same way as HTTP, explicit validation of the `Origin` header against the `Host` or `X-Forwarded-Host` is required to prevent hijacking when `cors` is False.
**Prevention:** Always validate the `Origin` header in the WebSocket handshake. If an application acts as a server on `localhost` or a specific domain, compare the `Origin`'s netloc against the `Host`/`X-Forwarded-Host` headers to ensure connections are only allowed from trusted origins (or explicitly opt-in to cross-origin access via a flag).
