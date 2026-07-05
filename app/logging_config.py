"""Basic application logging setup."""

import logging

_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once, in a simple structured-ish format.

    Safe to call multiple times; only the first call takes effect.
    """
    global _configured
    if _configured:
        return

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _configured = True
