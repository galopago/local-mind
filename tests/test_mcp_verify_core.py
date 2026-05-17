import unittest
from pathlib import Path

from mcp_package.link_core.mcp_verify import (
    display_command,
    mcp_verify_guidance,
    render_mcp_verify_text,
)


class McpVerifyCoreTests(unittest.TestCase):
    def test_guidance_reports_missing_sdk_and_version_mismatch(self):
        issues, actions = mcp_verify_guidance(
            target=Path("/tmp/link"),
            init_command=["python3", "link.py", "init", "/tmp/link"],
            expected_version="1.2.0",
            python_cmd="/tmp/Link Python/bin/python",
            import_status={"installed": True, "version": "1.1.0"},
            mcp_sdk_ready=False,
            version_matches=False,
            wiki_exists=True,
        )

        self.assertEqual([issue["code"] for issue in issues], ["mcp_sdk_missing", "version_mismatch"])
        self.assertEqual([action["tool"] for action in actions], ["reinstall_link_mcp", "upgrade_link_mcp"])
        self.assertIn("'/tmp/Link Python/bin/python'", actions[0]["command_text"])

    def test_render_ready_status(self):
        code, text = render_mcp_verify_text({
            "ready": True,
            "target": "/tmp/link",
            "python": "/tmp/python",
            "expected_version": "1.2.0",
            "version_matches": True,
            "link_mcp": {"installed": True, "version": "1.2.0", "mcp_sdk": True, "error": None},
            "wiki": {"path": "/tmp/link/wiki", "exists": True},
            "config": {"mcpServers": {"link": {"command": "/tmp/python", "args": ["-m", "link_mcp"]}}},
            "next_actions": [],
        })

        self.assertEqual(code, 0)
        self.assertIn("Link MCP verification: /tmp/link", text)
        self.assertIn("link-mcp: installed (1.2.0)", text)
        self.assertIn('"command": "/tmp/python"', text)
        self.assertIn("Result: ready", text)

    def test_render_missing_package_status(self):
        action = {
            "tool": "install_link_mcp",
            "command_text": "/tmp/python -m pip install --upgrade link-mcp",
        }
        code, text = render_mcp_verify_text({
            "ready": False,
            "target": "/tmp/link",
            "python": "/tmp/python",
            "expected_version": "1.2.0",
            "version_matches": False,
            "link_mcp": {"installed": False, "version": None, "mcp_sdk": False, "error": "No module named link_mcp"},
            "wiki": {"path": "/tmp/link/wiki", "exists": True},
            "config": {},
            "next_actions": [action],
        })

        self.assertEqual(code, 1)
        self.assertIn("link-mcp: missing", text)
        self.assertIn("Install: /tmp/python -m pip install --upgrade link-mcp", text)
        self.assertIn("macOS/Homebrew fallback", text)
        self.assertIn("Result: needs attention", text)

    def test_display_command_quotes_paths(self):
        text = display_command(["/tmp/Link Python/bin/python", "-m", "pip"])

        self.assertIn("'/tmp/Link Python/bin/python'", text)


if __name__ == "__main__":
    unittest.main()
