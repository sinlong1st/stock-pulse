"""Render collected news as a simple, self-contained HTML page."""

import re
from datetime import UTC, datetime
from html import escape

from app.models.article import NewsArticle
from app.pipeline.rule_filter import RelevanceResult


def _highlight(text: str, terms: list[str]) -> str:
    """HTML-escape `text`, wrapping any whole-word matches of `terms` in <strong>.

    Terms are matched case-insensitively; escaping is applied to every
    segment so the result is always safe HTML.
    """
    if not text:
        return ""
    if not terms:
        return escape(text)
    # Longest terms first so multi-word phrases win over their parts.
    ordered = sorted({t for t in terms if t}, key=len, reverse=True)
    pattern = re.compile(
        r"(?<!\w)(" + "|".join(re.escape(t) for t in ordered) + r")(?!\w)",
        re.IGNORECASE,
    )
    out: list[str] = []
    last = 0
    for match in pattern.finditer(text):
        out.append(escape(text[last : match.start()]))
        out.append(f"<strong>{escape(match.group(0))}</strong>")
        last = match.end()
    out.append(escape(text[last:]))
    return "".join(out)


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


def _render_chips(result: RelevanceResult | None) -> str:
    """Render match chips (tickers, macro, sector) for a relevant article."""
    if result is None or not result.is_relevant:
        return ""
    chips: list[str] = []
    for ticker in result.matched_tickers:
        chips.append(f'<span class="chip chip-ticker">{escape(ticker)}</span>')
    for macro in result.matched_macro:
        chips.append(f'<span class="chip chip-macro">{escape(macro)}</span>')
    for sector in result.matched_sectors:
        chips.append(f'<span class="chip chip-sector">{escape(sector)}</span>')
    return f'<div class="chips">{"".join(chips)}</div>'


def _render_card(article: NewsArticle, result: RelevanceResult | None = None) -> str:
    is_relevant = result is not None and result.is_relevant
    terms = result.highlights if is_relevant else []
    title = _highlight(article.title, terms)
    url = escape(article.url, quote=True)
    summary = _highlight(article.summary, terms) if article.summary else ""
    when = escape(_format_time(article.published_at))
    source = escape(article.source)
    summary_html = f'<p class="summary">{summary}</p>' if summary else ""
    relevant_class = " relevant" if is_relevant else " muted"
    data_relevant = "1" if is_relevant else "0"
    return f"""
      <article class="card{relevant_class}" data-relevant="{data_relevant}">
        <a class="title" href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>
        {summary_html}
        {_render_chips(result)}
        <div class="meta"><span>{source}</span><span>&middot;</span><span>{when}</span></div>
      </article>"""


def render_news_page(
    articles: list[NewsArticle],
    *,
    stored_total: int | None = None,
    evaluations: list[RelevanceResult] | None = None,
) -> str:
    """Return a full HTML document listing stored articles.

    When `evaluations` (rule-filter results, aligned with `articles`) is
    provided, relevant articles are highlighted with match chips.
    """
    results = evaluations if evaluations is not None else [None] * len(articles)
    cards = "\n".join(_render_card(a, r) for a, r in zip(articles, results)) or (
        '<p class="empty">No stored articles yet — click '
        "<strong>Fetch latest news</strong> to pull some in.</p>"
    )
    count = stored_total if stored_total is not None else len(articles)
    relevant = sum(1 for r in results if r is not None and r.is_relevant)
    relevant_note = f" &middot; {relevant} match the filter" if evaluations is not None else ""
    controls = (
        '<div class="controls">'
        '<input type="checkbox" id="only-matches">'
        f'<label for="only-matches">Only show matches ({relevant})</label>'
        "</div>"
        if evaluations is not None and relevant
        else ""
    )
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
  .card.relevant {{ border-left: 3px solid var(--accent); }}
  .card.muted {{ opacity: .55; }}
  .card.muted:hover {{ opacity: 1; }}
  .title strong, .summary strong {{ color: var(--accent); font-weight: 700; }}
  .controls {{ display: flex; align-items: center; gap: 8px; margin: 0 0 20px; }}
  .controls label {{ color: var(--muted); font-size: .88rem; cursor: pointer; user-select: none; }}
  body.only-matches .card[data-relevant="0"] {{ display: none; }}
  .chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }}
  .chip {{ font-size: .72rem; font-weight: 600; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }}
  .chip-ticker {{ background: rgba(76,154,255,.16); color: var(--accent); }}
  .chip-macro {{ background: rgba(240,170,60,.16); color: #e0972f; }}
  .chip-sector {{ background: rgba(120,200,120,.16); color: #4faf66; }}
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Stock<span class="pulse">Pulse</span></h1>
      <button id="fetch" class="refresh" type="button">↻ Fetch latest news</button>
    </header>
    <p class="sub" id="status">{count} stored articles{relevant_note} &middot; page loaded {generated}</p>
    {controls}
    {cards}
  </div>
  <script>
    const btn = document.getElementById('fetch');
    const status = document.getElementById('status');
    const only = document.getElementById('only-matches');
    if (only) {{
      only.addEventListener('change', () => {{
        document.body.classList.toggle('only-matches', only.checked);
      }});
    }}
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
