## 2024-05-18 - Prevent sensitive exception leakage
**Vulnerability:** Tool exception details are directly serialized to JSON and sent to the LLM/client, potentially leaking sensitive internal state, stack traces, or secrets embedded in error messages.
**Learning:** Returning `str(exc)` in a tool call's error response exposes the raw exception message directly to the agent runtime, which might reflect it back to a user.
**Prevention:** Log the raw exception with `exc_info=True` for debugging, but return a generic, safe error message to the LLM/client (e.g. `{"error": "An error occurred during tool execution."}`).
