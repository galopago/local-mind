import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.web_memory import (  # noqa: E402
    render_capture_card,
    render_memory_action_button,
    render_memory_card,
    render_memory_next_actions,
    render_memory_section,
)


def page_href(name: str) -> str:
    return f"/page/{name}"


class WebMemoryCoreTests(unittest.TestCase):
    def test_memory_card_escapes_content_and_renders_actions(self):
        record = {
            "name": "local-memory",
            "title": "<Local Memory>",
            "tldr": "Use <local> memory.",
            "memory_type": "preference",
            "scope": "user",
            "status": "active",
            "actions": [{
                "label": "Review",
                "kind": "review",
                "command": "link review-memory local-memory",
                "arguments": {"identifier": "local-memory"},
            }],
        }

        html = render_memory_card(record, page_href=page_href)

        self.assertIn('<a href="/page/local-memory">&lt;Local Memory&gt;</a>', html)
        self.assertIn("Use &lt;local&gt; memory.", html)
        self.assertIn('data-memory-action="review"', html)
        self.assertNotIn("<Local Memory>", html)

    def test_memory_section_uses_action_hints_when_record_has_no_actions(self):
        record = {"name": "agent-memory", "title": "Agent Memory"}

        html = render_memory_section(
            "Memories",
            [record],
            "No memories.",
            page_href=page_href,
            action_hints=lambda _record: [{
                "label": "Archive",
                "kind": "archive",
                "command": "link archive-memory agent-memory",
                "arguments": {"identifier": "agent-memory"},
            }],
            href="/inbox",
        )

        self.assertIn('<a href="/inbox">view all</a>', html)
        self.assertIn('data-memory-action="archive"', html)
        self.assertIn("link archive-memory agent-memory", html)

    def test_capture_card_escapes_warnings_and_commands(self):
        html = render_capture_card({
            "title": "Raw <Capture>",
            "path": "raw/memory-captures/session.md",
            "secret_warnings": ["OpenAI <key>"],
            "commands": {
                "accept": "accept-capture",
                "redact": "redact-capture",
            },
        })

        self.assertIn("Raw &lt;Capture&gt;", html)
        self.assertIn("OpenAI &lt;key&gt;", html)
        self.assertIn("accept-capture", html)
        self.assertNotIn("Raw <Capture>", html)

    def test_memory_action_button_requires_supported_kind_and_identifier(self):
        self.assertIn("Mark reviewed", render_memory_action_button({
            "kind": "review",
            "arguments": {"identifier": "one"},
        }))
        self.assertEqual("", render_memory_action_button({"kind": "forget", "arguments": {"identifier": "one"}}))
        self.assertEqual("", render_memory_action_button({"kind": "review", "arguments": {}}))

    def test_next_actions_render_commands(self):
        html = render_memory_next_actions([{
            "label": "Review",
            "detail": "Open inbox.",
            "command": "link memory-inbox",
            "href": "/inbox",
        }])

        self.assertIn('<a href="/inbox">Review</a>', html)
        self.assertIn("Open inbox.", html)
        self.assertIn("link memory-inbox", html)


if __name__ == "__main__":
    unittest.main()
