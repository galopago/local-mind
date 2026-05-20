"""HTML helpers for Link's local health page."""
from __future__ import annotations

import html
from collections.abc import Callable, Mapping

from .web_ingest import copy_button
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
    rows = "".join(
        "<li>"
        f"<code>{html.escape(command)}</code>"
        f"{copy_button(command, 'Copy')}"
        "</li>"
        for command in commands
    )
    return f'<section><h2>Repair Commands</h2><ul class="command-list">{rows}</ul></section>'


def _render_operation_actions(operations: Mapping[str, object]) -> str:
    actions = _dict_list(operations.get("next_actions"))
    if not actions:
        return ""
    rows = ""
    for action in actions:
        command = str(action.get("command") or "").strip()
        label = str(action.get("label") or command or "next action")
        command_html = f"<code>{html.escape(command)}</code>{copy_button(command, 'Copy')}" if command else ""
        rows += (
            "<li>"
            f"<strong>{html.escape(label)}</strong>"
            f"{command_html}"
            "</li>"
        )
    return f'<section><h2>Operation Next Actions</h2><ul class="command-list">{rows}</ul></section>'


def _render_validation_details(validation: Mapping[str, object]) -> str:
    if not validation.get("checked"):
        return "<section><h2>Validation Gate</h2><p>Validation has not been run in this status check.</p></section>"
    error_codes = [str(code) for code in validation.get("error_codes") or [] if str(code)]
    warning_codes = [str(code) for code in validation.get("warning_codes") or [] if str(code)]
    if not error_codes and not warning_codes:
        return "<section><h2>Validation Gate</h2><p>Validation passed with no errors or warnings.</p></section>"
    rows = "".join(
        f"<li><strong>{html.escape(kind)}</strong><span>{html.escape(', '.join(codes))}</span></li>"
        for kind, codes in (("Errors", error_codes), ("Warnings", warning_codes))
        if codes
    )
    return f'<section><h2>Validation Gate</h2><ul class="page-list">{rows}</ul></section>'


def _render_health_cards(status: Mapping[str, object], operations: Mapping[str, object]) -> str:
    validation = status.get("validation") if isinstance(status.get("validation"), dict) else {}
    ready_state = "done" if status.get("ready") else "blocked"
    validation_checked = bool(validation.get("checked"))
    validation_passed = bool(validation.get("passed"))
    validation_state = "done" if validation_checked and validation_passed else ("blocked" if validation_checked else "wait")
    stale_count = int(operations.get("stale_count") or 0)
    failed_count = int(operations.get("failed_count") or 0)
    active_count = int(operations.get("active_count") or 0)
    operations_state = "blocked" if stale_count or failed_count else ("next" if active_count else "done")
    needs_review_count = int(status.get("needs_review_count") or 0)
    memory_state = "next" if needs_review_count else "done"
    validation_detail = (
        f"{int(validation.get('error_count') or 0)} errors · {int(validation.get('warning_count') or 0)} warnings"
        if validation_checked
        else "run link status --validate"
    )
    cards = [
        (
            "Readiness",
            "ready" if status.get("ready") else "needs attention",
            ready_state,
            f"{status.get('content_page_count', 0)} content pages",
        ),
        (
            "Validation",
            "passed" if validation_passed else ("failed" if validation_checked else "not checked"),
            validation_state,
            validation_detail,
        ),
        (
            "Operations",
            "clear" if operations_state == "done" else ("active" if operations_state == "next" else "needs review"),
            operations_state,
            f"{stale_count} stale · {active_count} active",
        ),
        (
            "Memory Review",
            "clear" if not needs_review_count else f"{needs_review_count} pending",
            memory_state,
            f"{status.get('active_memory_count', 0)} active memories",
        ),
    ]
    rows = "".join(
        '<article class="health-card" data-state="'
        f'{html.escape(state, quote=True)}">'
        f"<strong>{html.escape(label)}</strong>"
        f"<span>{html.escape(value)}</span>"
        f"<small>{html.escape(detail)}</small>"
        "</article>"
        for label, value, state, detail in cards
    )
    return f'<section class="health-cards" aria-label="Health summary">{rows}</section>'


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
        f"{_render_health_cards(status, operations)}"
        f"{stats}"
        "<section><h2>Readiness</h2>"
        '<ul class="page-list">'
        f"<li><strong>Search backend</strong><span>{html.escape(str(status.get('search_backend') or 'unknown'))}</span></li>"
        f"<li><strong>Schema</strong><span>{html.escape(str(schema.get('status') or 'unknown'))}</span></li>"
        f"<li><strong>Active memories</strong><span>{html.escape(str(status.get('active_memory_count') or 0))}</span></li>"
        f"<li><strong>Interrupted operations</strong><span>{html.escape(str(operations.get('stale_count') or 0))} stale · {html.escape(str(operations.get('active_count') or 0))} active</span></li>"
        "</ul></section>"
        f"{_render_validation_details(validation)}"
        f"{_render_issue_list('Warnings', warnings, 'No readiness warnings.')}"
        f"{_render_issue_list('Interrupted Operations', operation_items, 'No pending, failed, or interrupted Link operations.')}"
        f"{_render_operation_actions(operations)}"
        f"{_render_issue_list('Next Actions', next_actions, 'No repair actions needed.')}"
        f"{_render_commands(commands)}"
    )
    return layout("Health", body)
