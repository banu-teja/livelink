## 2025-02-27 - [Base64 Decoding of User Input]
**Vulnerability:** A Denial of Service (DoS) vulnerability via `base64.b64decode` in `WebSocketTransport._parse_input`.
**Learning:** In `src/livelink/transport.py`, `_parse_input` decodes a base64 string provided in `message["data"]`. `b64decode` has strict validation and raises a `binascii.Error` if the string contains non-base64 characters or has incorrect padding. The exception is unhandled and bubbles up, crashing the WebSocket event loop.
**Prevention:** Always validate and catch exceptions when handling unverified user input. A base64 input should have a try-except block to gracefully discard the malformed message rather than bringing down the connection.
