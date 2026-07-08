"""Alert channel and status constants.

Re-exported from the dependency-free ``app.status`` leaf module so the db
layer can import the constants without triggering the alerts package
(which would create an import cycle).
"""

from app.status import (
    CHANNEL_TELEGRAM,
    STATUS_ACKNOWLEDGED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENT,
)

__all__ = [
    "CHANNEL_TELEGRAM",
    "STATUS_PENDING",
    "STATUS_SENT",
    "STATUS_FAILED",
    "STATUS_ACKNOWLEDGED",
]
