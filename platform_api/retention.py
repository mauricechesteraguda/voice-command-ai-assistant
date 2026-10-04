"""Retention classes: telemetry 30 days, administrative audit 365 days."""

# implementation-10042026-Maurice
from datetime import timedelta
from .observability import traced
RETENTION = {"telemetry": timedelta(days=30), "audit": timedelta(days=365)}

@traced
def retention_days(record_class: str) -> int:
    return RETENTION[record_class].days
