"""Alerting: decision policy, records, and (later) delivery channels."""

from app.alerts.constants import (
    CHANNEL_TELEGRAM,
    STATUS_ACKNOWLEDGED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENT,
)
from app.alerts.policy import AlertDecision, AlertPolicy, get_alert_policy
from app.alerts.router import DeliveryResult, send_pending_alerts
from app.alerts.telegram import (
    Notifier,
    NotifierError,
    TelegramNotifier,
    build_telegram_notifier,
)

__all__ = [
    "CHANNEL_TELEGRAM",
    "STATUS_PENDING",
    "STATUS_SENT",
    "STATUS_FAILED",
    "STATUS_ACKNOWLEDGED",
    "AlertDecision",
    "AlertPolicy",
    "get_alert_policy",
    "DeliveryResult",
    "send_pending_alerts",
    "Notifier",
    "NotifierError",
    "TelegramNotifier",
    "build_telegram_notifier",
]
