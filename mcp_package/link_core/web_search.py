"""HTML helpers for Link's local search page."""
from __future__ import annotations

import html
import re
import urllib.parse
from collections.abc import Callable, Sequence

from .web_ingest import copy_button


PageHref = Callable[[str], str]
PageLayout = Callable[[str, str], str]


def highlight_search_term(text: str, term: str) -> str:
    """Wrap all occurrences of term in mark tags, escaping all other text."""
    if not term or not text:
        return html.escape(text)
    parts = re.split(f"({re.escape(term)})", text, flags=re.IGNORECASE)
    return "".join(
        f"<mark>{html.escape(part)}</mark>" if part.lower() == term.lower() else html.escape(part)
        for part in parts
    )


def render_search_page(
    query: str,
    results: Sequence[dict[str, object]],
    *,
    page_href: PageHref,
    layout: PageLayout,
    limit: int = 30,
) -> str:
    """Render the local search page for a bounded result set."""
    normalized = query.lower().strip()
    if not normalized:
        return layout(
            "Search",
            '<div class="breadcrumb"><a href="/">Link</a> / search</div>'
            '<h1>Search</h1><p>Enter a search term above.</p>',
        )

    total = len(results)
    cap_note = f" (showing {limit} of {total})" if total > limit else ""
    graph_href = "/graph?q=" + urllib.parse.quote(query)
    brief_href = "/brief?q=" + urllib.parse.quote(query)
    actions = (
        '<div class="page-actions">'
        f'<a class="button-link" href="{html.escape(graph_href, quote=True)}">Open graph search</a>'
        f'<a class="button-link" href="{html.escape(brief_href, quote=True)}">Open memory brief</a>'
        f'{copy_button(f"query Link for {query}", "Copy query prompt")}'
        "</div>"
    )
    items = "".join(
        f'<li><a href="{html.escape(page_href(str(result["name"])), quote=True)}">'
        f'{highlight_search_term(str(result["title"]), query)}</a>'
        f'<br><small style="color:#888">...{highlight_search_term(str(result.get("snippet", "")), query)}...</small></li>'
        for result in results[:limit]
    )
    return layout(
        f"Search: {query}",
        f'<div class="breadcrumb"><a href="/">Link</a> / search</div>'
        f'<h1>Search: {html.escape(query)}</h1>'
        f'<p>{total} result{"s" if total != 1 else ""}{cap_note}</p>'
        f'{actions}'
        f'<ul class="page-list search-results">{items}</ul>',
    )
