"""HTML helpers for Link wiki page lists."""
from __future__ import annotations

import html
from collections.abc import Callable, Mapping, Sequence


PageHref = Callable[[str], str]
PageLayout = Callable[[str, str], str]


def render_wiki_page(
    title: str,
    *,
    category: str,
    meta: Mapping[str, object],
    body_html: str,
    layout: PageLayout,
) -> str:
    """Render a single wiki page shell around already-rendered Markdown."""
    crumb = '<div class="breadcrumb"><a href="/">Link</a>'
    if category:
        crumb += f" / {html.escape(category)}"
    crumb += f" / {html.escape(title)}</div>"
    meta_line = render_page_meta_line(meta)
    return layout(title, crumb + meta_line + body_html)


def render_page_meta_line(meta: Mapping[str, object]) -> str:
    """Render compact page metadata shown under the breadcrumb."""
    parts: list[str] = []
    if meta.get("type"):
        parts.append(f'<span class="badge">{html.escape(str(meta["type"]))}</span>')
    if meta.get("maturity"):
        parts.append(html.escape(str(meta["maturity"])))
    if meta.get("source_count"):
        parts.append(f'{html.escape(str(meta["source_count"]))} sources')
    if meta.get("date_updated"):
        parts.append(f'updated {html.escape(str(meta["date_updated"]))}')
    aliases = meta.get("aliases", [])
    if isinstance(aliases, list) and aliases:
        parts.append("also: " + ", ".join(html.escape(str(alias)) for alias in aliases))
    elif isinstance(aliases, str) and aliases:
        parts.append(f"also: {html.escape(aliases)}")
    return f'<div class="meta">{" · ".join(parts)}</div>' if parts else ""


def render_all_pages(
    pages: Sequence[dict[str, object]],
    *,
    total: int,
    limit: int,
    offset: int,
    page_href: PageHref,
    layout: PageLayout,
    error: str = "",
) -> str:
    """Render the paginated all-pages view."""
    items = "".join(
        f'<li><a href="{html.escape(page_href(str(page["name"])), quote=True)}">'
        f'{html.escape(str(page["title"]))}</a>'
        f'<span class="type">{html.escape(str(page.get("type") or page.get("category") or ""))}</span></li>'
        for page in pages
    )
    controls = render_page_controls(total=total, limit=limit, offset=offset)
    warning = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return layout(
        "All Pages",
        '<div class="breadcrumb"><a href="/">Link</a> / all pages</div>'
        f"<h1>All Pages ({total})</h1>{warning}{controls}<ul class='page-list'>{items}</ul>{controls}",
    )


def render_page_controls(*, total: int, limit: int, offset: int) -> str:
    """Render previous/next controls for a bounded page window."""
    if total <= limit and offset <= 0:
        return ""

    start = 0 if total == 0 else offset + 1
    end = min(offset + limit, total)
    next_offset = offset + limit
    prev_offset = max(0, offset - limit)
    prev_href = html.escape(f"/all?limit={limit}&offset={prev_offset}", quote=True)
    next_href = html.escape(f"/all?limit={limit}&offset={next_offset}", quote=True)
    prev_link = (
        f'<a class="button-link" href="{prev_href}">Previous</a>'
        if offset > 0
        else '<span class="button-link disabled">Previous</span>'
    )
    next_link = (
        f'<a class="button-link" href="{next_href}">Next</a>'
        if next_offset < total
        else '<span class="button-link disabled">Next</span>'
    )
    return f'<div class="pager"><span>Showing {start}-{end} of {total}</span>{prev_link}{next_link}</div>'
