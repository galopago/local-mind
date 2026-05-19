"""HTML helpers for Link's local health page."""
from __future__ import annotations

import html
from collections.abc import Callable, Mapping

from .web_layout import render_stat_grid


PageLayout = Callable[[str, str], str]


def _dict_list(value: object) -> list[dict[str, object]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _render_issue_list(title: str, items: list[dict[str, object]], empty: str) -> str:
    if not items:
        return f"<section><h2>{html.escape(title)}</h2><p>{html.escape(empty)}</p></section>"
    rows = ""
    for item in items:
        code = str(item.get("code") or item.get("operation") or item.get("label") or "issue")
        message = str(item.get("message") or item.get("description") or item.get("detail") or item.get("command") or "")
        detail = str(item.get("detail") or item.get("marker") or item.get("tool") or "").strip()
        rows += (
            "<li>"
            f"<strong>{html.escape(code)}</strong>"
            f"<span>{html.escape(message)}</span>"
            f"{f'<code>{html.escape(detail)}</code>' if detail else ''}"
            "</li>"
        )
    return f'<section><h2>{html.escape(title)}</h2><ul class="page-list">{rows}</ul></section>'


def _render_commands(commands: list[str]) -> str:
    escaped = "\n".join(html.escape(command) for command in commands)
    return f"<section><h2>Repair Commands</h2><pre><code>{escaped}</code></pre></section>"


def render_health_page(
    status: Mapping[str, object],
    operations: Mapping[str, object],
    *,
    layout: PageLayout,
) -> str:
    """Render a human-readable health and readiness page for the local viewer."""
    validation = status.get("validation") if isinstance(status.get("validation"), dict) else {}
    schema = status.get("schema") if isinstance(status.get("schema"), dict) else {}
    ready = "yes" if status.get("ready") else "no"
    validation_label = "passed" if validation.get("passed") else "not checked"
    if validation.get("checked") and not validation.get("passed"):
        validation_label = "failed"
    stats = render_stat_grid([
        (ready, "ready"),
        (status.get("content_page_count", 0), "content pages"),
        (status.get("memory_count", 0), "memories"),
        (status.get("needs_review_count", 0), "review"),
        (operations.get("operation_count", 0), "operations"),
        (validation_label, "validation"),
    ])
    warnings = _dict_list(status.get("warnings"))
    next_actions = _dict_list(status.get("next_actions"))
    operation_items = _dict_list(operations.get("operations"))
    commands = [
        "link status --validate",
        "link operations",
        "link doctor --fix",
        "link validate",
        "link benchmark \"agent memory\"",
    ]
    body = (
        '<div class="breadcrumb"><a href="/">Link</a> / health</div>'
        "<h1>Health</h1>"
        '<p class="summary">One local check for readiness, validation, interrupted writes, and repair commands.</p>'
        f"{stats}"
        "<section><h2>Readiness</h2>"
        '<ul class="page-list">'
        f"<li><strong>Search backend</strong><span>{html.escape(str(status.get('search_backend') or 'unknown'))}</span></li>"
        f"<li><strong>Schema</strong><span>{html.escape(str(schema.get('status') or 'unknown'))}</span></li>"
        f"<li><strong>Active memories</strong><span>{html.escape(str(status.get('active_memory_count') or 0))}</span></li>"
        f"<li><strong>Interrupted operations</strong><span>{html.escape(str(operations.get('stale_count') or 0))} stale · {html.escape(str(operations.get('active_count') or 0))} active</span></li>"
        "</ul></section>"
        f"{_render_issue_list('Warnings', warnings, 'No readiness warnings.')}"
        f"{_render_issue_list('Interrupted Operations', operation_items, 'No pending, failed, or interrupted Link operations.')}"
        f"{_render_issue_list('Next Actions', next_actions, 'No repair actions needed.')}"
        f"{_render_commands(commands)}"
    )
    return layout("Health", body)
