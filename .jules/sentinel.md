## 2024-05-18 - Overly Permissive CORS Configuration
**Vulnerability:** The `Access-Control-Allow-Origin` header is hardcoded to `*` when CORS is enabled in `src/livelink/serve.py`.
**Learning:** Setting CORS to `*` allows any website to make cross-origin requests to the API, which can lead to data exfiltration or unauthorized actions if the user's browser has stored credentials or active sessions.
**Prevention:** Allow users to specify a list of allowed origins or a regex pattern to validate the origin header, rather than defaulting to `*`. If CORS is truly meant to be public, document this clearly, but typically APIs should restrict access to trusted domains.
