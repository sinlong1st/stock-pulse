"""Send push notifications through the Expo Push API.

Best-effort and isolated behind an injectable transport, like every other
outbound client (testable with ``httpx.MockTransport``). Never raises — a push
failure must not break the alert pipeline.
"""

import logging

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger("stockpulse.push.notifier")

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


async def send_push(
    tokens: list[str],
    *,
    title: str,
    body: str,
    data: dict | None = None,
    settings: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
    timeout: float = 15.0,
) -> int:
    """Send one notification to many tokens. Returns the number attempted.

    Never raises: on a transport/HTTP error it logs and returns 0.
    """
    settings = settings or get_settings()
    tokens = [t for t in tokens if t]
    if not tokens:
        return 0

    messages = [
        {"to": token, "title": title, "body": body, "data": data or {}, "sound": "default"}
        for token in tokens
    ]
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if settings.expo_access_token:
        headers["Authorization"] = f"Bearer {settings.expo_access_token}"

    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            resp = await client.post(_EXPO_PUSH_URL, json=messages, headers=headers)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Push send failed: %s", exc)
        return 0

    logger.info("Sent %d push notification(s).", len(messages))
    return len(messages)
