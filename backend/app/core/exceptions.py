from typing import Any, Dict, Optional


class StreamShieldError(Exception):
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class AuthenticationError(StreamShieldError):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, "AUTH_ERROR", 401)


class AuthorizationError(StreamShieldError):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, "FORBIDDEN", 403)


class NotFoundError(StreamShieldError):
    def __init__(self, resource: str = "Resource"):
        super().__init__(f"{resource} not found", "NOT_FOUND", 404)


class ValidationError(StreamShieldError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "VALIDATION_ERROR", 422)
        self.details = details or {}


class RateLimitError(StreamShieldError):
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, "RATE_LIMIT", 429)


class ThreatDetectedError(StreamShieldError):
    def __init__(self, message: str, threat_type: str, score: float):
        super().__init__(message, "THREAT_DETECTED", 403)
        self.threat_type = threat_type
        self.score = score
