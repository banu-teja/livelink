## 2023-10-27 - [Add CSWSH protection to WebSocket server]
**Vulnerability:** Cross-Site WebSocket Hijacking (CSWSH) could occur because the custom WebSocket HTTP request processor (`process_request`) lacked an `Origin` check against the `Host` headers when CORS is disabled.
**Learning:** By default, custom `websockets` HTTP handler overrides (like `process_request` in `websockets.asyncio.server`) bypass standard browser CORS checks on WebSocket handshakes, leading to the risk of hijacking cross-origin requests.
**Prevention:** Always parse and explicitly check `Origin` against the network location of the `Host` or `X-Forwarded-Host` headers in any custom HTTP handler overriding WebSocket handshakes unless CORS is intentionally enabled across all origins.
