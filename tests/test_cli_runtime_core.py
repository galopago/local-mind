import unittest

from mcp_package.link_core.cli_runtime import (
    render_demo_text,
    render_init_text,
    render_starter_prompts_text,
)


class CliRuntimeCoreTests(unittest.TestCase):
    def test_render_init_text(self):
        code, text = render_init_text(target="/tmp/link", fixes=["created wiki/index.md"])

        self.assertEqual(code, 0)
        self.assertIn("Link wiki ready at /tmp/link", text)
        self.assertIn("Initialized:", text)
        self.assertIn("link status --validate", text)

    def test_render_starter_prompts_text(self):
        code, text = render_starter_prompts_text({
            "target": "/tmp/link",
            "project": "link",
            "prompts": [{
                "prompt": "is Link ready?",
                "when": "first run",
            }],
            "commands": ["link status --validate"],
        })

        self.assertEqual(code, 0)
        self.assertIn("Link starter prompts: /tmp/link", text)
        self.assertIn("Project: link", text)
        self.assertIn("- is Link ready?", text)
        self.assertIn("- link status --validate", text)

    def test_render_demo_text(self):
        code, text = render_demo_text(
            target="/tmp/link-demo",
            guide_path="/tmp/link-demo/START_HERE.md",
            serve_command="python3 link.py serve /tmp/link-demo",
            query_command="python3 link.py query 'why does Link help agents?' /tmp/link-demo --budget small",
            brief_command="python3 link.py brief 'working on agent memory' /tmp/link-demo",
            audit_command="python3 link.py memory-audit /tmp/link-demo",
        )

        self.assertEqual(code, 0)
        self.assertIn("Link demo created at /tmp/link-demo", text)
        self.assertIn("Try the value loop:", text)
        self.assertIn("/tmp/link-demo/START_HERE.md", text)
        self.assertIn("http://127.0.0.1:3000/graph", text)


if __name__ == "__main__":
    unittest.main()
