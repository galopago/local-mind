import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.web_pages import render_all_pages, render_page_controls, render_wiki_page  # noqa: E402


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
    )

    assert "<title>All Pages</title>" in html
    assert "All Pages (1)" in html
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
