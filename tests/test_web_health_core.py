import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.web_health import render_health_page  # noqa: E402


def _layout(title: str, body: str) -> str:
    return f"<title>{title}</title>{body}"


def test_render_health_page_shows_readiness_operations_and_commands():
    html = render_health_page(
        {
            "ready": False,
            "content_page_count": 12,
            "memory_count": 2,
            "active_memory_count": 2,
            "needs_review_count": 1,
            "search_backend": "sqlite-fts",
            "schema": {"status": "current"},
            "validation": {"checked": True, "passed": False},
            "warnings": [{"code": "stale_operations", "message": "1 operation needs review.", "detail": "remember"}],
            "next_actions": [{"label": "validate wiki", "tool": "validate_wiki"}],
        },
        {
            "operation_count": 1,
            "stale_count": 1,
            "active_count": 0,
            "operations": [{"operation": "remember", "description": "Save memory", "marker": "remember-1.json"}],
        },
        layout=_layout,
    )

    assert "<h1>Health</h1>" in html
    assert "sqlite-fts" in html
    assert "stale_operations" in html
    assert "remember-1.json" in html
    assert "link operations" in html
    assert "link benchmark &quot;agent memory&quot;" in html
