"""Lightweight read-only web views for local debugging.

This is intentionally minimal — a window onto what the pipeline produces,
not the future dashboard described in the technical plan.
"""

from app.web.views import render_news_page

__all__ = ["render_news_page"]
