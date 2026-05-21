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
    assert '/graph?q=link' in html
    assert '/brief?q=link' in html
    assert 'data-copy-text="query Link for link"' in html
    assert "Copy query prompt" in html
    assert "/page/page-0" in html
    assert "/page/page-1" in html
    assert "/page/page-2" not in html
    assert "&lt;agent memory&gt;" in html
    assert "<mark>Link</mark>" in html


def test_render_search_page_no_results_guides_recovery():
    html = render_search_page("meeting notes", [], page_href=lambda name: f"/page/{name}", layout=_layout)

    assert "<p>0 results</p>" in html
    assert "No matching pages yet" in html
    assert 'href="/ingest"' in html
    assert 'data-copy-text="ingest the new raw Link files"' in html
    assert 'data-copy-text="propose memories about meeting notes from Link raw sources"' in html
    assert "Copy ingest prompt" in html
    assert "Copy memory proposal prompt" in html


def test_render_search_page_escapes_actions_and_result_hrefs():
    html = render_search_page(
        'agent "memory"',
        [{"name": 'bad"name', "title": "Agent", "snippet": "memory"}],
        page_href=lambda name: f'/page/{name}?x="bad"',
        layout=_layout,
    )

    assert '/graph?q=agent%20%22memory%22' in html
    assert 'data-copy-text="query Link for agent &quot;memory&quot;"' in html
    assert '/page/bad&quot;name?x=&quot;bad&quot;' in html
