"""HTML helpers for Link's local memory web views."""
from __future__ import annotations

import html
from collections.abc import Callable, Sequence


MemoryActionHints = Callable[[dict[str, object]], list[dict[str, object]]]
PageHref = Callable[[str], str]


def render_memory_action_button(action: dict[str, object]) -> str:
    kind = str(action.get("kind") or "")
    if kind not in {"review", "archive", "restore"}:
        return ""
    arguments = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
    identifier = str(arguments.get("identifier") or "")
    if not identifier:
        return ""
    labels = {
        "review": "Mark reviewed",
        "archive": "Archive",
        "restore": "Restore",
    }
    return (
        f'<button type="button" data-memory-action="{html.escape(kind, quote=True)}" '
        f'data-memory="{html.escape(identifier, quote=True)}">'
        f'{html.escape(labels[kind])}</button>'
    )


def render_memory_action_commands(actions: Sequence[dict[str, object]]) -> str:
    if not actions:
        return ""
    rows = ""
    for action in actions:
        label = html.escape(str(action.get("label") or ""))
        if action.get("href"):
            label_html = f'<a href="{html.escape(str(action["href"]))}">{label}</a>'
        else:
            label_html = label
        priority = str(action.get("priority") or "")
        priority_html = f'<span class="memory-meta">{html.escape(priority)}</span>' if priority else ""
        button_html = render_memory_action_button(action)
        rows += (
            f'<div class="memory-action-row"><span class="memory-action-head"><strong>{label_html}</strong>'
            f'{priority_html}{button_html}</span>'
            f'<code>{html.escape(str(action.get("command") or ""))}</code></div>'
        )
    return f'<div class="memory-actions">{rows}</div>'


def render_memory_card(
    record: dict[str, object],
    *,
    page_href: PageHref,
    action_hints: MemoryActionHints | None = None,
    include_issues: bool = False,
) -> str:
    name = str(record.get("name") or "")
    title = str(record.get("title") or name)
    summary = str(record.get("tldr") or record.get("snippet") or "")
    meta_parts = [
        str(record.get("memory_type") or "note"),
        str(record.get("scope") or "user"),
        str(record.get("status") or "active"),
    ]
    if record.get("updated_at"):
        meta_parts.append(f'updated {record["updated_at"]}')
    elif record.get("date_captured"):
        meta_parts.append(f'captured {record["date_captured"]}')
    meta = " · ".join(part for part in meta_parts if part)
    issues_html = ""
    if include_issues and record.get("issues"):
        issues_html = "<ul class='memory-issues'>" + "".join(
            f'<li><span class="severity">{html.escape(str(issue["severity"]))}</span> '
            f'{html.escape(str(issue["code"]))}: {html.escape(str(issue["message"]))}</li>'
            for issue in record["issues"]
            if isinstance(issue, dict)
        ) + "</ul>"
    actions = render_memory_action_commands(record.get("actions") or (action_hints(record) if action_hints else []))
    summary_html = f'<p class="summary">{html.escape(summary)}</p>' if summary else ""
    return (
        '<article class="memory-card">'
        f'<h3><a href="{page_href(name)}">{html.escape(title)}</a></h3>'
        f'<div class="memory-meta">{html.escape(meta)}</div>'
        f'{summary_html}'
        f'{issues_html}'
        f'{actions}'
        '</article>'
    )


def render_memory_section(
    title: str,
    records: list[dict[str, object]],
    empty: str,
    *,
    page_href: PageHref,
    action_hints: MemoryActionHints | None = None,
    href: str = "",
    include_issues: bool = False,
) -> str:
    heading_link = f'<a href="{html.escape(href)}">view all</a>' if href else ""
    heading = f'<div class="section-heading"><h2>{html.escape(title)}</h2>{heading_link}</div>'
    if not records:
        return heading + f"<p>{html.escape(empty)}</p>"
    cards = "".join(
        render_memory_card(record, page_href=page_href, action_hints=action_hints, include_issues=include_issues)
        for record in records
    )
    return heading + f'<div class="memory-grid">{cards}</div>'


def render_capture_card(capture: dict[str, object]) -> str:
    title = html.escape(str(capture.get("title") or capture.get("path") or "Raw capture"))
    path = html.escape(str(capture.get("path") or ""))
    meta_parts = ["raw capture"]
    if capture.get("project"):
        meta_parts.append(f'project {capture["project"]}')
    if capture.get("date_captured"):
        meta_parts.append(f'captured {capture["date_captured"]}')
    warnings = [str(label) for label in capture.get("secret_warnings") or []]
    if warnings:
        meta_parts.append("secret warnings")
    meta = " · ".join(meta_parts)
    warning_html = ""
    if warnings:
        warning_html = (
            '<p class="summary"><strong>Secret-looking values:</strong> '
            + html.escape(", ".join(warnings))
            + "</p>"
        )
    commands = capture.get("commands") or {}
    actions = "".join(
        f'<div><strong>{html.escape(label)}</strong><code>{html.escape(str(command))}</code></div>'
        for label, command in (
            ("Accept proposal", commands.get("accept", "")),
            ("Redact", commands.get("redact", "")),
            ("Delete", commands.get("delete", "")),
        )
        if command
    )
    return (
        '<article class="memory-card">'
        f'<h3>{title}</h3>'
        f'<div class="memory-meta">{html.escape(meta)}</div>'
        f'<p class="summary"><code>{path}</code></p>'
        f'{warning_html}'
        f'<div class="memory-actions">{actions}</div>'
        '</article>'
    )


def render_capture_section(captures: list[dict[str, object]]) -> str:
    heading = '<div class="section-heading"><h2>Raw captures</h2></div>'
    if not captures:
        return heading + "<p>No saved raw captures.</p>"
    cards = "".join(render_capture_card(capture) for capture in captures)
    return heading + f'<div class="memory-grid">{cards}</div>'


def render_memory_next_actions(actions: list[dict[str, str]]) -> str:
    items = ""
    for action in actions:
        label = html.escape(action["label"])
        if action.get("href"):
            label_html = f'<a href="{html.escape(action["href"])}">{label}</a>'
        else:
            label_html = label
        items += (
            f'<li><strong>{label_html}</strong>: {html.escape(action["detail"])}'
            f'<br><code>{html.escape(action["command"])}</code></li>'
        )
    return f'<div class="memory-next"><strong>Next actions</strong><ul>{items}</ul></div>'
