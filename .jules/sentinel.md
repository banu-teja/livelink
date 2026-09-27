## 2024-05-24 - Overly Permissive CORS Configuration

**Vulnerability:** In `src/livelink/serve.py`, when `cors` is enabled (`cors=True`), the `Access-Control-Allow-Origin` header is set to `*`. This allows any domain to access the resources via cross-origin requests, which can lead to Cross-Site Request Forgery (CSRF) or unintended data exposure if the endpoints handle sensitive data.

**Learning:** This existed because `cors=True` is a simple boolean flag in the `serve` function, defaulting to an overly permissive configuration when turned on. It did not support specifying an explicit list of allowed origins.

**Prevention:** CORS configurations should default to secure values, allowing specific origins rather than a wildcard `*`. If CORS needs to be enabled, it should accept a list of allowed origins or, at the very least, allow the user to define the exact origins rather than enforcing `*` when a simple boolean flag is passed.
