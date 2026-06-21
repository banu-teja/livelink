class RelayKitError(Exception):
    pass


class AuthenticationError(RelayKitError):
    pass


class SessionNotReadyError(RelayKitError):
    pass


class SessionExpiredError(RelayKitError):
    pass


class SessionBusyError(RelayKitError):
    """Raised when send/stream is called while another operation is in progress."""

    pass


class InvalidStateError(RelayKitError):
    """Raised on an invalid connection state transition."""

    pass


class AdapterError(RelayKitError):
    pass


class UnsupportedFormatError(RelayKitError):
    pass


class UnsupportedModalityError(RelayKitError):
    pass


class ConnectionError(RelayKitError):
    pass


class RateLimitError(RelayKitError):
    pass
