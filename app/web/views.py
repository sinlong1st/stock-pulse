"""Render collected news as a simple, self-contained HTML page."""

import re
from datetime import UTC, datetime
from html import escape

from app.db.repository import AlertView
from app.models.article import NewsArticle
from app.models.classification import ClassificationResult
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


def _render_verdict(classification: ClassificationResult | None) -> str:
    """Render the AI verdict block (importance + why it matters)."""
    if classification is None:
        return ""
    importance = escape(classification.importance)
    category = escape(classification.category)
    why = escape(classification.why_it_matters)
    bell = " 🔔 alert" if classification.should_alert else ""
    return f"""
        <div class="verdict verdict-{importance}">
          <span class="badge badge-{importance}">{importance}</span>
          <span class="cat">{category}</span>
          <span class="alert-flag">{bell}</span>
          <p class="why"><strong>Why it matters:</strong> {why}</p>
        </div>"""


def _render_card(
    article: NewsArticle,
    result: RelevanceResult | None = None,
    classification: ClassificationResult | None = None,
) -> str:
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
    # One-line digest (shown in compact mode): importance + AI summary.
    digest_html = ""
    if classification is not None:
        imp = escape(classification.importance)
        digest_html = (
            f'<div class="digest-line"><span class="badge badge-{imp}">{imp}</span>'
            f'<span class="digest-summary">{escape(classification.summary)}</span></div>'
        )
    return f"""
      <article class="card{relevant_class}" data-relevant="{data_relevant}">
        <a class="title" href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>
        {digest_html}
        {summary_html}
        {_render_chips(result)}
        {_render_verdict(classification)}
        <div class="meta"><span>{source}</span><span>&middot;</span><span>{when}</span></div>
      </article>"""


def render_news_page(
    articles: list[NewsArticle],
    *,
    stored_total: int | None = None,
    evaluations: list[RelevanceResult] | None = None,
    classifications: dict[str, ClassificationResult] | None = None,
) -> str:
    """Return a full HTML document listing stored articles.

    When `evaluations` (rule-filter results, aligned with `articles`) is
    provided, relevant articles are highlighted with match chips. When
    `classifications` (keyed by article id) is provided, classified
    articles also show the AI verdict.
    """
    results = evaluations if evaluations is not None else [None] * len(articles)
    class_map = classifications or {}
    cards = "\n".join(
        _render_card(a, r, class_map.get(a.id or "")) for a, r in zip(articles, results)
    ) or (
        '<p class="empty">No stored articles yet — click '
        "<strong>Fetch latest news</strong> to pull some in.</p>"
    )
    count = stored_total if stored_total is not None else len(articles)
    shown = len(articles)
    relevant = sum(1 for r in results if r is not None and r.is_relevant)
    classified = len(class_map)
    relevant_note = f" &middot; {relevant} match the filter" if evaluations is not None else ""
    if classified:
        relevant_note += f" &middot; {classified} AI-analyzed"

    # Default to a compact digest, showing only matches (when there are any).
    # Toggles switch to full cards and reveal every article.
    only_matches_default = evaluations is not None and relevant > 0
    classes = ["compact"]
    if only_matches_default:
        classes.append("only-matches")
    body_class = " ".join(classes)

    control_items = []
    if articles:
        control_items.append(
            '<label class="ctl"><input type="checkbox" id="compact" checked> Compact digest</label>'
        )
    if only_matches_default:
        control_items.append(
            '<label class="ctl"><input type="checkbox" id="show-all"> '
            f"Show all &middot; {relevant} of {shown} match</label>"
        )
    controls = f'<div class="controls">{"".join(control_items)}</div>' if control_items else ""
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
  .controls {{ display: flex; align-items: center; gap: 18px; margin: 0 0 20px; flex-wrap: wrap; }}
  .controls .ctl {{ color: var(--muted); font-size: .88rem; cursor: pointer; user-select: none; display: inline-flex; align-items: center; gap: 6px; }}
  body.only-matches .card[data-relevant="0"] {{ display: none; }}
  /* Compact digest: one skimmable line per item. */
  .digest-line {{ display: flex; align-items: center; gap: 8px; margin-top: 8px; }}
  .digest-summary {{ color: var(--muted); font-size: .9rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  body:not(.compact) .digest-line {{ display: none; }}
  body.compact .card {{ padding: 10px 14px; margin-bottom: 8px; }}
  body.compact .title {{ font-size: .98rem; }}
  body.compact .summary, body.compact .chips, body.compact .verdict, body.compact .meta {{ display: none; }}
  .actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .refresh.accent {{ color: #a06bff; border-color: rgba(150,110,255,.4); }}
  .chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }}
  .verdict {{ margin-top: 12px; padding: 10px 12px; border-radius: 8px; background: rgba(127,127,127,.08); }}
  .badge {{ font-size: .72rem; font-weight: 800; padding: 2px 8px; border-radius: 6px; letter-spacing: .03em; }}
  .badge-LOW {{ background: rgba(150,160,175,.2); color: var(--muted); }}
  .badge-MEDIUM {{ background: rgba(76,154,255,.2); color: var(--accent); }}
  .badge-HIGH {{ background: rgba(240,150,50,.2); color: #e0872f; }}
  .badge-CRITICAL {{ background: rgba(240,70,70,.22); color: #ef5252; }}
  .cat {{ font-size: .72rem; color: var(--muted); margin-left: 8px; letter-spacing: .04em; }}
  .alert-flag {{ font-size: .72rem; color: #e0872f; margin-left: 8px; }}
  .why {{ font-size: .9rem; margin: 8px 0 0; color: var(--text); }}
  .why strong {{ color: var(--muted); font-weight: 600; }}
  .chip {{ font-size: .72rem; font-weight: 600; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }}
  .chip-ticker {{ background: rgba(76,154,255,.16); color: var(--accent); }}
  .chip-macro {{ background: rgba(240,170,60,.16); color: #e0972f; }}
  .chip-sector {{ background: rgba(120,200,120,.16); color: #4faf66; }}
</style>
</head>
<body class="{body_class}">
  <div class="wrap">
    <header>
      <h1>Stock<span class="pulse">Pulse</span></h1>
      <div class="actions">
        <button id="fetch" class="refresh" type="button">↻ Fetch latest news</button>
        <button id="analyze" class="refresh accent" type="button">✨ Analyze with AI</button>
        <a class="refresh" href="/alerts">🔔 Alerts</a>
      </div>
    </header>
    <p class="sub" id="status">{count} stored articles{relevant_note} &middot; page loaded {generated}</p>
    {controls}
    {cards}
  </div>
  <script>
    const btn = document.getElementById('fetch');
    const status = document.getElementById('status');
    const showAll = document.getElementById('show-all');
    if (showAll) {{
      // Default view shows only matches; checking "Show all" reveals everything.
      showAll.addEventListener('change', () => {{
        document.body.classList.toggle('only-matches', !showAll.checked);
      }});
    }}

    const compact = document.getElementById('compact');
    if (compact) {{
      compact.addEventListener('change', () => {{
        document.body.classList.toggle('compact', compact.checked);
      }});
    }}

    const analyze = document.getElementById('analyze');
    analyze.addEventListener('click', async () => {{
      if (!confirm('Send the latest unanalyzed matches to the AI? This uses a small amount of OpenAI credit.')) return;
      analyze.disabled = true;
      analyze.textContent = 'Analyzing…';
      try {{
        const res = await fetch('/classify?limit=5', {{ method: 'POST' }});
        const data = await res.json();
        if (data.error) {{
          status.textContent = data.error + (data.hint ? ' — ' + data.hint : '');
          analyze.disabled = false;
          analyze.textContent = '✨ Analyze with AI';
          return;
        }}
        status.textContent = `AI analyzed ${{data.classified}} article(s), ${{data.errors}} error(s) — reloading…`;
        setTimeout(() => location.reload(), 900);
      }} catch (err) {{
        analyze.disabled = false;
        analyze.textContent = '✨ Analyze with AI';
        status.textContent = 'Analyze failed — is the server running?';
      }}
    }});
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


_ALERT_STATUS_ORDER = ["PENDING", "SENT", "FAILED", "ACKNOWLEDGED"]


def _render_alert_row(alert: AlertView) -> str:
    title = escape(alert.article_title)
    url = escape(alert.url, quote=True)
    importance = escape(alert.importance)
    status = escape(alert.status)
    channel = escape(alert.channel)
    created = escape(_format_time(alert.created_at))
    sent = f" &middot; sent {escape(_format_time(alert.sent_at))}" if alert.sent_at else ""
    error = (
        f'<p class="why"><strong>Error:</strong> {escape(alert.error_message)}</p>'
        if alert.error_message
        else ""
    )
    return f"""
      <article class="card" data-status="{status}">
        <div class="alert-head">
          <span class="badge badge-{importance}">{importance}</span>
          <span class="status status-{status}">{status}</span>
          <span class="cat">{channel}</span>
        </div>
        <a class="title" href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>
        {error}
        <div class="meta"><span>created {created}{sent}</span></div>
      </article>"""


def render_alerts_page(alerts: list[AlertView]) -> str:
    """Return a full HTML document listing alert records and their status."""
    counts = {status: 0 for status in _ALERT_STATUS_ORDER}
    for alert in alerts:
        counts[alert.status] = counts.get(alert.status, 0) + 1
    summary = " &middot; ".join(f"{counts.get(s, 0)} {s.lower()}" for s in _ALERT_STATUS_ORDER)

    rows = "\n".join(_render_alert_row(a) for a in alerts) or (
        '<p class="empty">No alerts yet. Classify some matching articles on the '
        '<a href="/">news page</a> to generate alerts.</p>'
    )
    pending = counts.get("PENDING", 0)
    generated = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>StockPulse — Alerts</title>
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
  body {{ margin: 0; background: var(--bg); color: var(--text);
    font: 16px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }}
  .wrap {{ max-width: 760px; margin: 0 auto; padding: 32px 20px 64px; }}
  header {{ display: flex; align-items: baseline; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 8px; }}
  h1 {{ font-size: 1.6rem; margin: 0; }}
  h1 .pulse {{ color: var(--accent); }}
  .sub {{ color: var(--muted); font-size: .9rem; margin: 0 0 24px; }}
  .actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .refresh {{ color: var(--accent); text-decoration: none; border: 1px solid var(--border);
    padding: 6px 14px; border-radius: 8px; font-size: .9rem; white-space: nowrap; cursor: pointer; background: transparent; }}
  .refresh:hover {{ border-color: var(--accent); }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; margin-bottom: 12px; }}
  .alert-head {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
  .title {{ color: var(--text); text-decoration: none; font-weight: 600; font-size: 1.02rem; display: block; }}
  .title:hover {{ color: var(--accent); }}
  .meta {{ color: var(--muted); font-size: .82rem; margin-top: 10px; }}
  .why {{ font-size: .9rem; margin: 8px 0 0; color: var(--text); }}
  .why strong {{ color: #ef5252; font-weight: 600; }}
  .empty {{ color: var(--muted); text-align: center; padding: 48px 0; }}
  .empty a, .sub a {{ color: var(--accent); }}
  .cat {{ font-size: .72rem; color: var(--muted); letter-spacing: .04em; }}
  .badge {{ font-size: .72rem; font-weight: 800; padding: 2px 8px; border-radius: 6px; }}
  .badge-LOW {{ background: rgba(150,160,175,.2); color: var(--muted); }}
  .badge-MEDIUM {{ background: rgba(76,154,255,.2); color: var(--accent); }}
  .badge-HIGH {{ background: rgba(240,150,50,.2); color: #e0872f; }}
  .badge-CRITICAL {{ background: rgba(240,70,70,.22); color: #ef5252; }}
  .status {{ font-size: .72rem; font-weight: 700; padding: 2px 8px; border-radius: 999px; }}
  .status-PENDING {{ background: rgba(240,170,60,.18); color: #e0972f; }}
  .status-SENT {{ background: rgba(120,200,120,.18); color: #4faf66; }}
  .status-FAILED {{ background: rgba(240,70,70,.2); color: #ef5252; }}
  .status-ACKNOWLEDGED {{ background: rgba(76,154,255,.18); color: var(--accent); }}
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Stock<span class="pulse">Pulse</span> Alerts</h1>
      <div class="actions">
        <a class="refresh" href="/">← News</a>
        <button id="send" class="refresh" type="button">📨 Send pending ({pending})</button>
      </div>
    </header>
    <p class="sub" id="status">{summary} &middot; page loaded {generated}</p>
    {rows}
  </div>
  <script>
    const status = document.getElementById('status');
    const send = document.getElementById('send');
    send.addEventListener('click', async () => {{
      if (!confirm('Send all pending alerts to Telegram now?')) return;
      send.disabled = true;
      send.textContent = 'Sending…';
      try {{
        const res = await fetch('/alerts/send', {{ method: 'POST' }});
        const data = await res.json();
        if (data.error) {{
          status.textContent = data.error + (data.hint ? ' — ' + data.hint : '');
          send.disabled = false;
          send.textContent = '📨 Send pending';
          return;
        }}
        status.textContent = `Sent ${{data.sent}}, failed ${{data.failed}} (of ${{data.processed}}) — reloading…`;
        setTimeout(() => location.reload(), 900);
      }} catch (err) {{
        send.disabled = false;
        send.textContent = '📨 Send pending';
        status.textContent = 'Send failed — is the server running?';
      }}
    }});
  </script>
</body>
</html>"""
