"""LLM provider error hierarchy."""


class LLMError(Exception):
    """Base class for all LLM provider errors."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMTimeoutError(LLMError):
    """Request exceeded the configured timeout."""

    def __init__(self, message: str = "LLM request timed out") -> None:
        super().__init__(message, retryable=True)


class LLMRateLimitError(LLMError):
    """Provider rate limit was exceeded."""

    def __init__(self, message: str = "LLM rate limit exceeded") -> None:
        super().__init__(message, retryable=True)


class LLMProviderError(LLMError):
    """Non-retryable provider error (bad request, auth failure, etc.)."""

    def __init__(
        self, message: str, *, status_code: int | None = None
    ) -> None:
        super().__init__(message, retryable=False)
        self.status_code = status_code


class LLMOutputError(LLMError):
    """LLM returned a response that could not be parsed as valid JSON."""

    def __init__(self, message: str = "LLM output is not valid JSON") -> None:
        super().__init__(message, retryable=True)
