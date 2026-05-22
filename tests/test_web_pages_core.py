import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.web_pages import (  # noqa: E402
    render_all_pages,
    render_page_catalog_summary,
    render_page_controls,
    render_page_groups,
    render_page_outline,
    render_wiki_page,
)


def _layout(title: str, body: str) -> str:
    return f"<title>{title}</title>{body}"


def test_render_all_pages_escapes_page_fields():
    pages = [
        {"name": "safe-page", "title": "<Link>", "type": "<script>", "category": "concepts"},
    ]

    html = render_all_pages(
        pages,
        total=1,
        limit=250,
        offset=0,
        page_href=lambda name: f"/page/{name}",
        layout=_layout,
        type_counts={"<script>": 1},
    )

    assert "<title>All Pages</title>" in html
    assert "All Pages (1)" in html
    assert "catalog-summary" in html
    assert "page-group" in html
    assert "&lt;Link&gt;" in html
    assert "&lt;script&gt;" in html
    assert "<script>" not in html


def test_render_all_pages_includes_error_and_pagination():
    pages = [
        {"name": "topic-025", "title": "Topic 025", "type": "concept", "category": "concepts"},
    ]

    html = render_all_pages(
        pages,
        total=302,
        limit=25,
        offset=25,
        page_href=lambda name: f"/page/{name}",
        layout=_layout,
        error="Invalid <limit>",
    )

    assert "Showing 26-50 of 302" in html
    assert "/all?limit=25&amp;offset=0" in html
    assert "/all?limit=25&amp;offset=50" in html
    assert "Invalid &lt;limit&gt;" in html
    assert "Topic 025" in html


def test_render_all_pages_groups_visible_pages_by_type():
    pages = [
        {"name": "agent-memory", "title": "Agent memory", "type": "concept", "category": "concepts"},
        {"name": "release-notes", "title": "Release notes", "type": "source", "category": "sources"},
        {"name": "local-first", "title": "Local-first", "type": "concept", "category": "concepts"},
    ]

    html = render_all_pages(
        pages,
        total=3,
        limit=250,
        offset=0,
        page_href=lambda name: f"/page/{name}",
        layout=_layout,
        type_counts={"concept": 2, "source": 1},
    )

    assert '<span class="catalog-chip"><strong>concept</strong>2</span>' in html
    assert "<h2>concept <span>2</span></h2>" in html
    assert "<h2>source <span>1</span></h2>" in html
    assert html.index("Agent memory") < html.index("Release notes")


def test_render_page_catalog_summary_is_empty_without_counts():
    assert render_page_catalog_summary(total=10, visible=5, type_counts=None) == ""


def test_render_page_groups_handles_empty_catalog():
    html = render_page_groups([], page_href=lambda name: f"/page/{name}")

    assert "No pages found." in html


def test_render_page_controls_is_empty_without_pagination():
    assert render_page_controls(total=1, limit=250, offset=0) == ""


def test_render_wiki_page_escapes_breadcrumb_and_meta():
    html = render_wiki_page(
        "<Title>",
        category="<concepts>",
        meta={
            "type": "<concept>",
            "maturity": "<seed>",
            "source_count": "<2>",
            "date_updated": "<today>",
            "aliases": ["<alias>", "Link"],
        },
        body_html="<h1>Trusted body</h1>",
        layout=_layout,
    )

    assert "&lt;concepts&gt;" in html
    assert "&lt;Title&gt;" in html
    assert "&lt;concept&gt;" in html
    assert "&lt;seed&gt;" in html
    assert "&lt;2&gt; sources" in html
    assert "updated &lt;today&gt;" in html
    assert "also: &lt;alias&gt;, Link" in html
    assert "<h1>Trusted body</h1>" in html
    assert "<concept>" not in html


def test_render_wiki_page_includes_local_graph_action():
    html = render_wiki_page(
        "Agent Memory",
        category="concepts",
        meta={},
        body_html="<p>Trusted body</p>",
        layout=_layout,
        graph_href='/graph?focus=agent-memory&depth=2',
        query_prompt="query Link for Agent Memory",
    )

    assert '<a class="button-link" href="/graph?focus=agent-memory&amp;depth=2">Open local graph</a>' in html
    assert 'data-copy-text="query Link for Agent Memory"' in html
    assert "Copy query prompt" in html
    assert "<p>Trusted body</p>" in html


def test_render_wiki_page_includes_memory_proposal_action():
    html = render_wiki_page(
        "Release Notes",
        category="sources",
        meta={},
        body_html="<p>Trusted body</p>",
        layout=_layout,
        proposal_href="/propose?source=raw/release-notes.md",
        proposal_prompt="propose memories from raw/release-notes.md",
    )

    assert '<a class="button-link" href="/propose?source=raw/release-notes.md">Propose memories</a>' in html
    assert 'data-copy-text="propose memories from raw/release-notes.md"' in html
    assert "Copy memory prompt" in html


def test_render_wiki_page_escapes_query_prompt_action():
    html = render_wiki_page(
        "Unsafe",
        category="concepts",
        meta={},
        body_html="<p>Trusted body</p>",
        layout=_layout,
        query_prompt='query Link for "<unsafe>"',
    )

    assert 'data-copy-text="query Link for &quot;&lt;unsafe&gt;&quot;"' in html
    assert 'query Link for "<unsafe>"' not in html


def test_render_wiki_page_adds_document_outline_for_sectioned_pages():
    html = render_wiki_page(
        "Sectioned",
        category="concepts",
        meta={},
        body_html="<h1>Sectioned</h1><h2>Summary</h2><p>One</p><h2>Raw Source</h2><p>Two</p>",
        layout=_layout,
    )

    assert 'class="wiki-page-shell"' in html
    assert 'class="page-outline"' in html
    assert '<h2 id="summary">Summary</h2>' in html
    assert '<h2 id="raw-source">Raw Source</h2>' in html
    assert '<a class="level-2" href="#summary">Summary</a>' in html


def test_render_page_outline_escapes_labels_and_deduplicates_slugs():
    outline, body = render_page_outline(
        "<h2>Use &lt;Link&gt;</h2><p>x</p><h2>Use &lt;Link&gt;</h2>"
    )

    assert 'href="#use-link"' in outline
    assert 'href="#use-link-2"' in outline
    assert "Use &lt;Link&gt;" in outline
    assert '<h2 id="use-link">Use &lt;Link&gt;</h2>' in body
    assert '<h2 id="use-link-2">Use &lt;Link&gt;</h2>' in body
