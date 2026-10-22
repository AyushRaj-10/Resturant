"""Domain exceptions for business and service layer operations."""

from typing import Optional


class ServiceError(Exception):
    """Base class for all domain and service exceptions."""

    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__


class NotFoundError(ServiceError):
    """Raised when a requested resource does not exist in the database."""

    def __init__(self, message: str = "Resource not found", code: str = "NOT_FOUND"):
        super().__init__(message=message, code=code)


class ValidationRuleError(ServiceError):
    """Raised when an operation violates a domain or business validation rule."""

    def __init__(self, message: str, code: str = "VALIDATION_FAILED"):
        super().__init__(message=message, code=code)


class ConflictError(ServiceError):
    """Raised when an operation conflicts with existing resource state."""

    def __init__(self, message: str, code: str = "CONFLICT"):
        super().__init__(message=message, code=code)
