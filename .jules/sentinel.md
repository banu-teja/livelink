## 2023-11-01 - [CSWSH]
**Vulnerability:** Cross-Site WebSocket Hijacking missing Origin validation
**Learning:** By default, websockets server doesn't validate origins automatically if implemented directly in a custom handler without explicitly doing it.
**Prevention:** Always validate `Origin` header against `Host`/`X-Forwarded-Host` during the WebSocket handshake in `process_request` or similar, ensuring it fails closed on exception and correctly parses IPv6 addresses.
