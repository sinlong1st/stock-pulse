"""Render collected news as a simple, self-contained HTML page."""

from datetime import UTC, datetime
from html import escape

from app.models.article import NewsArticle


def _format_time(published: datetime | None) -> str:
    """Human-friendly relative time, e.g. '3h ago'."""
    if published is None:
        return "unknown time"
    if published.tzinfo is None:  # be robust to naive datetimes
        published = published.replace(tzinfo=UTC)
    delta = datetime.now(tz=UTC) - published
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _render_card(article: NewsArticle) -> str:
    title = escape(article.title)
    url = escape(article.url, quote=True)
    summary = escape(article.summary) if article.summary else ""
    when = escape(_format_time(article.published_at))
    source = escape(article.source)
    summary_html = f'<p class="summary">{summary}</p>' if summary else ""
    return f"""
      <article class="card">
        <a class="title" href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>
        {summary_html}
        <div class="meta"><span>{source}</span><span>&middot;</span><span>{when}</span></div>
      </article>"""


def render_news_page(articles: list[NewsArticle], *, stored_total: int | None = None) -> str:
    """Return a full HTML document listing stored articles."""
    cards = "\n".join(_render_card(a) for a in articles) or (
        '<p class="empty">No stored articles yet — click '
        "<strong>Fetch latest news</strong> to pull some in.</p>"
    )
    count = stored_total if stored_total is not None else len(articles)
    generated = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>StockPulse — Latest News</title>
<style>
  :root {{
    --bg: #0f1115; --card: #1a1e27; --border: #2a2f3a;
    --text: #e6e8ec; --muted: #9aa4b2; --accent: #4c9aff;
  }}
  @media (prefers-color-scheme: light) {{
    :root {{
      --bg: #f4f6fa; --card: #ffffff; --border: #e2e6ee;
      --text: #1a1e27; --muted: #66707e; --accent: #1a6dff;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text);
    font: 16px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  }}
  .wrap {{ max-width: 760px; margin: 0 auto; padding: 32px 20px 64px; }}
  header {{ display: flex; align-items: baseline; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 8px; }}
  h1 {{ font-size: 1.6rem; margin: 0; }}
  h1 .pulse {{ color: var(--accent); }}
  .sub {{ color: var(--muted); font-size: .9rem; margin: 0 0 24px; }}
  .refresh {{
    color: var(--accent); text-decoration: none; border: 1px solid var(--border);
    padding: 6px 14px; border-radius: 8px; font-size: .9rem; white-space: nowrap;
  }}
  .refresh:hover {{ border-color: var(--accent); }}
  .card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px 18px; margin-bottom: 12px;
  }}
  .title {{ color: var(--text); text-decoration: none; font-weight: 600; font-size: 1.05rem; display: block; }}
  .title:hover {{ color: var(--accent); }}
  .summary {{ color: var(--muted); font-size: .92rem; margin: 8px 0 0; }}
  .meta {{ color: var(--muted); font-size: .82rem; margin-top: 10px; display: flex; gap: 8px; }}
  .empty {{ color: var(--muted); text-align: center; padding: 48px 0; }}
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Stock<span class="pulse">Pulse</span></h1>
      <button id="fetch" class="refresh" type="button">↻ Fetch latest news</button>
    </header>
    <p class="sub" id="status">{count} stored articles &middot; page loaded {generated}</p>
    {cards}
  </div>
  <script>
    const btn = document.getElementById('fetch');
    const status = document.getElementById('status');
    btn.addEventListener('click', async () => {{
      btn.disabled = true;
      btn.textContent = 'Fetching…';
      try {{
        const res = await fetch('/collect');
        const data = await res.json();
        status.textContent = `+${{data.new}} new, ${{data.duplicates}} duplicates skipped `
          + `(${{data.stored_total}} stored total) — reloading…`;
        setTimeout(() => location.reload(), 800);
      }} catch (err) {{
        btn.disabled = false;
        btn.textContent = '↻ Fetch latest news';
        status.textContent = 'Fetch failed — is the server running?';
      }}
    }});
  </script>
</body>
</html>"""
