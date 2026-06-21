class LiveLinkError(Exception):
    pass


class AuthenticationError(LiveLinkError):
    pass


class SessionNotReadyError(LiveLinkError):
    pass


class SessionExpiredError(LiveLinkError):
    pass


class SessionBusyError(LiveLinkError):
    """Raised when send/stream is called while another operation is in progress."""

    pass


class InvalidStateError(LiveLinkError):
    """Raised on an invalid connection state transition."""

    pass


class AdapterError(LiveLinkError):
    pass


class UnsupportedFormatError(LiveLinkError):
    pass


class UnsupportedModalityError(LiveLinkError):
    pass


class ConnectionError(LiveLinkError):
    pass


class RateLimitError(LiveLinkError):
    pass
