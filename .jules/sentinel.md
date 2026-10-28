## 2025-02-24 - Cross-Site WebSocket Hijacking Protection
**Vulnerability:** The custom WebSocket server (`serve.py`) was not validating the `Origin` header when CORS was disabled, making it potentially vulnerable to Cross-Site WebSocket Hijacking (CSWSH).
**Learning:** Python websockets library does not perform automatic Origin validation when accepting raw connections. When handling websockets manually, explicitly verifying `Origin` against `Host` (or `X-Forwarded-Host`) is critical.
**Prevention:** Implement an origin mismatch check during the HTTP handshake phase before accepting WebSocket connections unless CORS is intentionally enabled.
