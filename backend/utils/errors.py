"""Typed application errors mapped to HTTP status codes."""


class ApiError(Exception):
    """Base class for all expected API errors."""
    status = 400

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        if status is not None:
            self.status = status

    def to_dict(self) -> dict:
        return {"error": self.message}


class ValidationError(ApiError):
    status = 422


class Unauthorized(ApiError):
    status = 401


class Forbidden(ApiError):
    status = 403


class NotFound(ApiError):
    status = 404


class Conflict(ApiError):
    status = 409


class RateLimited(ApiError):
    status = 429