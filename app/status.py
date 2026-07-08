"""Shared alert channel/status constants.

A dependency-free leaf module so both the db and alerts layers can import
these without creating an import cycle.
"""

# Delivery channels.
CHANNEL_TELEGRAM = "telegram"

# Alert lifecycle statuses.
STATUS_PENDING = "PENDING"
STATUS_SENT = "SENT"
STATUS_FAILED = "FAILED"
STATUS_ACKNOWLEDGED = "ACKNOWLEDGED"
