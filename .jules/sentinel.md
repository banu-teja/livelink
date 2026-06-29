## 2024-05-24 - [Unauthenticated Supervision API]
**Vulnerability:** The `/supervise/{session_id}` endpoint in `agent.serve()` has no authentication mechanism, exposing internal supervision controls (cancel, inspect, replay) to anyone who can guess or obtain a session ID.
**Learning:** WebSocket endpoints that expose administrative or supervisory control over sessions must require authentication, just like REST endpoints. Session IDs (UUID4) provide some protection against guessing but are insufficient as the sole security boundary for privileged actions.
**Prevention:** Implement authentication/authorization on the WebSocket upgrade request (e.g., via query parameters, headers, or cookies) before accepting the connection.
