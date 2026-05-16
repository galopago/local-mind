import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.web_memory_pages import (  # noqa: E402
    render_brief_page,
    render_captures_page,
    render_inbox_page,
    render_memory_audit_page,
    render_memory_dashboard_page,
    render_profile_page,
)


def _layout(title: str, body: str) -> str:
    return f"<title>{title}</title>{body}"


def _page_href(name: str) -> str:
    return f"/page/{name}"


def _action_hints(_record: dict[str, object]) -> list[dict[str, object]]:
    return []


def test_render_brief_page_escapes_query_and_project():
    payload = {
        "project": "<alpha>",
        "profile": {"active_count": 2},
        "captures": {"count": 0, "items": []},
        "review": {"count": 1, "items": []},
        "relevant_count": 1,
        "agent_guidance": ["Use <Link> first"],
        "relevant_memories": [],
    }

    html = render_brief_page(payload, "<task>", page_href=_page_href, action_hints=_action_hints, layout=_layout)

    assert "<title>Memory Brief</title>" in html
    assert "value=\"&lt;task&gt;\"" in html
    assert "Project:</strong> &lt;alpha&gt;" in html
    assert "Use &lt;Link&gt; first" in html
    assert "<task>" not in html


def test_render_memory_dashboard_page_shows_counts_next_actions_and_sections():
    payload = {
        "project": "alpha",
        "memory_count": 3,
        "active_count": 2,
        "review_count": 1,
        "updated_count": 1,
        "capture_count": 0,
        "archived_count": 0,
        "by_type": {"preference": 2},
        "by_scope": {"project": 1},
        "next_actions": [{"label": "Review", "detail": "Confirm memory", "command": "link memory-inbox"}],
        "review": [],
        "captures": [],
        "recent_updates": [],
        "active": [],
        "archived": [],
    }

    html = render_memory_dashboard_page(payload, page_href=_page_href, action_hints=_action_hints, layout=_layout)

    assert "Memory Dashboard" in html
    assert '<span class="num">3</span><span class="label">memories</span>' in html
    assert "<strong>Types:</strong> preference: 2" in html
    assert "link memory-inbox" in html
    assert "No memories need review." in html


def test_render_profile_page_lists_memory_sections_and_explain_links():
    record = {
        "name": "prefer-short-notes",
        "title": "Prefer short notes",
        "memory_type": "preference",
        "scope": "user",
        "tldr": "Keep release notes short.",
    }
    payload = {
        "project": "",
        "memory_count": 1,
        "active_count": 1,
        "review_count": 0,
        "by_type": {"preference": 1},
        "by_scope": {"user": 1},
        "by_status": {"active": 1},
        "recent": [record],
        "preferences": [record],
        "decisions": [],
        "projects": [],
        "archived": [],
    }

    html = render_profile_page(payload, page_href=_page_href, layout=_layout)

    assert "Memory Profile" in html
    assert "/page/prefer-short-notes" in html
    assert "/explain-memory?memory=prefer-short-notes" in html
    assert "Keep release notes short." in html


def test_render_memory_audit_page_reports_risks():
    payload = {
        "project": "alpha",
        "status": "needs_attention",
        "profile": {"memory_count": 1, "active_count": 1, "review_count": 1},
        "captures": {"count": 0, "warning_count": 0, "read_warning_count": 0, "items": []},
        "risk_factors": [{"code": "stale", "message": "Review <memory>"}],
        "next_actions": [],
        "inbox": {"items": []},
    }

    html = render_memory_audit_page(payload, page_href=_page_href, action_hints=_action_hints, layout=_layout)

    assert "Memory Audit" in html
    assert "needs_attention" in html
    assert "Review &lt;memory&gt;" in html


def test_render_captures_page_shows_redaction_and_read_warnings():
    payload = {
        "project": "alpha",
        "count": 1,
        "warning_count": 1,
        "read_warning_count": 1,
        "captures": [],
        "read_warnings": [{"capture": "raw/memory-captures/bad.md", "error": "<denied>"}],
    }

    html = render_captures_page(payload, layout=_layout)

    assert "Raw Capture Inbox" in html
    assert "1 raw capture contains secret-looking values" in html
    assert "raw/memory-captures/bad.md" in html
    assert "&lt;denied&gt;" in html


def test_render_inbox_page_lists_review_items_and_actions():
    payload = {
        "project": "",
        "review_count": 1,
        "counts_by_severity": {"warning": 1},
        "items": [
            {
                "name": "memory-one",
                "title": "Memory <One>",
                "memory_type": "preference",
                "scope": "user",
                "status": "pending",
                "tldr": "Needs review.",
                "issues": [{"severity": "warning", "code": "pending", "message": "Needs <review>"}],
                "primary_action": {"label": "Review", "description": "Confirm it"},
                "actions": [{"label": "Mark reviewed", "command": "link review-memory memory-one"}],
            }
        ],
    }

    html = render_inbox_page(payload, page_href=_page_href, layout=_layout)

    assert "Memory Review Inbox" in html
    assert "Memory &lt;One&gt;" in html
    assert "Needs &lt;review&gt;" in html
    assert "/explain-memory?memory=memory-one" in html
    assert "link review-memory memory-one" in html
