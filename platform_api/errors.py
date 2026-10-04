"""Typed, privacy-safe failures shared by control-plane boundaries."""

# implementation-10042026-platform-contract-errors
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .observability import traced

logger = logging.getLogger("control_plane.errors")


class ErrorCode(str, Enum):
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CONFLICT = "CONFLICT"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class SafeError:
    """An externally safe error; exception messages and paths never cross it."""

    code: ErrorCode
    status: int
    remediation: str
    correlation_id: str
    idempotency_key: str | None = None

    def as_dict(self) -> dict[str, Any]:
        logger.info("error.serialized")
        result: dict[str, Any] = {
            "error_code": self.code.value,
            "remediation": self.remediation,
            "correlation_id": self.correlation_id,
        }
        if self.idempotency_key:
            result["idempotency_key"] = self.idempotency_key
        return result


class PlatformError(Exception):
    """Typed internal failure with a redacted external representation."""

    def __init__(self, code: ErrorCode, remediation: str, *, status: int = 500, idempotency_key: str | None = None) -> None:
        logger.info("error.created")
        super().__init__(code.value)
        self.code = code
        self.remediation = remediation
        self.status = status
        self.idempotency_key = idempotency_key


@traced
def classify_error(exc: BaseException) -> ErrorCode:
    """Map boundary exceptions to stable codes without retaining their text."""
    logger.info("error.classified")
    if isinstance(exc, PermissionError):
        return ErrorCode.AUTHENTICATION_FAILED
    if isinstance(exc, ValueError):
        return ErrorCode.VALIDATION_FAILED
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return ErrorCode.DEPENDENCY_UNAVAILABLE
    return ErrorCode.INTERNAL_ERROR


@traced
def safe_error(exc: BaseException, *, correlation_id: str, idempotency_key: str | None = None) -> SafeError:
    """Build a path-free error envelope suitable for an HTTP response."""
    logger.info("error.enveloped")
    if isinstance(exc, PlatformError):
        return SafeError(exc.code, exc.status, exc.remediation, correlation_id, idempotency_key or exc.idempotency_key)
    code = classify_error(exc)
    status = 401 if code is ErrorCode.AUTHENTICATION_FAILED else 422 if code is ErrorCode.VALIDATION_FAILED else 503 if code is ErrorCode.DEPENDENCY_UNAVAILABLE else 500
    return SafeError(code, status, "retry or contact the platform operator", correlation_id, idempotency_key)


@traced
def log_error(error: SafeError) -> None:
    """Emit only stable, non-content fields for operational diagnosis."""
    logger.info(json.dumps({"event": "control_plane.error", **error.as_dict(), "status": error.status}, sort_keys=True))
