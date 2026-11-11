## 2024-11-12 - [CSWSH Origin Null Bypass]
**Vulnerability:** A CSWSH validation check that checks if `origin_host and target_host` before comparing them can be bypassed if the `Origin` header is `"null"` because `urllib.parse.urlparse("null").hostname` is `None`. Also, blindly trusting `X-Forwarded-Host` for CSWSH validation is insecure without proxy validation.
**Learning:** `Origin: null` is a common bypass for CSWSH protection using iframes with `sandbox="allow-scripts"`.
**Prevention:** Explicitly check for and reject `Origin: null`, and avoid using `X-Forwarded-Host` blindly.