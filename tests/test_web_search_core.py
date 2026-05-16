import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.web_search import highlight_search_term, render_search_page  # noqa: E402


def _layout(title: str, body: str) -> str:
    return f"<title>{title}</title>{body}"


def test_highlight_search_term_escapes_text_and_marks_matches():
    html = highlight_search_term("<Link> memory link", "link")

    assert "&lt;" in html
    assert "<mark>Link</mark>" in html
    assert "<mark>link</mark>" in html


def test_render_search_page_handles_empty_query():
    html = render_search_page("", [], page_href=lambda name: f"/page/{name}", layout=_layout)

    assert "<title>Search</title>" in html
    assert "Enter a search term above." in html


def test_render_search_page_caps_results_and_escapes_content():
    results = [
        {"name": f"page-{index}", "title": f"Link {index}", "snippet": "<agent memory>"}
        for index in range(3)
    ]

    html = render_search_page("link", results, page_href=lambda name: f"/page/{name}", layout=_layout, limit=2)

    assert "3 results (showing 2 of 3)" in html
    assert "/page/page-0" in html
    assert "/page/page-1" in html
    assert "/page/page-2" not in html
    assert "&lt;agent memory&gt;" in html
    assert "<mark>Link</mark>" in html
