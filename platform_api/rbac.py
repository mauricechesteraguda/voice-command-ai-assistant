"""Least-privilege roles for the versioned API."""

# implementation-10042026-Maurice
from enum import Enum
from .observability import traced

class Role(str, Enum):
    VIEWER = "Viewer"
    OPERATOR = "Operator"
    ADMIN = "Admin"

PERMISSIONS = {
    Role.VIEWER: frozenset({"read:config", "read:telemetry", "read:devices"}),
    Role.OPERATOR: frozenset({"read:config", "read:telemetry", "read:devices", "write:device", "write:cohort"}),
    Role.ADMIN: frozenset({"read:config", "read:telemetry", "read:devices", "write:device", "write:cohort", "write:config", "read:audit"}),
}

@traced
def allows(role: str, permission: str) -> bool:
    try:
        return permission in PERMISSIONS[Role(role)]
    except ValueError:
        return False
