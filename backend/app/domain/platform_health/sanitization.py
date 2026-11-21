"""Sanitize monitor diagnostics before returning them to authenticated clients."""

from __future__ import annotations

import re


_SENSITIVE_ERROR_PATTERNS = (
    (
        re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?(?:bearer\s+)?)[^\"'\s,;}]+"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)((?:access[_-]?token|refresh[_-]?token|api[_-]?key|client[_-]?secret|password|token|secret|key|code)=)[^&\s,;]+"),
        r"\1[REDACTED]",
    ),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[REDACTED_API_KEY]"),
)


def sanitize_diagnostic(message: str, *, limit: int = 500) -> str:
    safe = (message or "")[:limit]
    for pattern, replacement in _SENSITIVE_ERROR_PATTERNS:
        safe = pattern.sub(replacement, safe)
    return safe
