import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLERS = [
    ROOT / "integrations/antigravity/install.sh",
    ROOT / "integrations/claude-code/install.sh",
    ROOT / "integrations/codex/install.sh",
    ROOT / "integrations/copilot/install.sh",
    ROOT / "integrations/cursor/install.sh",
    ROOT / "integrations/kiro/install.sh",
    ROOT / "integrations/vscode/install.sh",
]


class InstallerTests(unittest.TestCase):
    def test_scaffold_does_not_use_break_system_packages(self):
        scaffold = (ROOT / "integrations/_shared/scaffold.sh").read_text(encoding="utf-8")

        self.assertNotIn("--break-system-packages", scaffold)
        self.assertIn(".link-mcp-venv", scaffold)
        self.assertIn(".link-mcp-python", scaffold)

    def test_installers_read_resolved_mcp_python_marker(self):
        for installer in INSTALLERS:
            with self.subTest(installer=installer.name):
                text = installer.read_text(encoding="utf-8")
                self.assertIn("MCP_PYTHON", text)
                self.assertIn(".link-mcp-python", text)

    def test_codex_and_kiro_update_existing_mcp_registration(self):
        codex = (ROOT / "integrations/codex/install.sh").read_text(encoding="utf-8")
        kiro = (ROOT / "integrations/kiro/install.sh").read_text(encoding="utf-8")

        self.assertIn("pattern.sub(block, text)", codex)
        self.assertNotIn("! grep -q '\\[mcp_servers.link\\]'", codex)
        self.assertNotIn("Link MCP already registered", kiro)

    def test_codex_mcp_registration_pattern_compiles_and_replaces_block(self):
        codex = (ROOT / "integrations/codex/install.sh").read_text(encoding="utf-8")
        match = re.search(r"pattern = re\.compile\((r\"[^\"]+\")\)", codex)
        self.assertIsNotNone(match)

        pattern = re.compile(ast.literal_eval(match.group(1)))
        existing_config = (
            '[mcp_servers.link]\n'
            'command = "python3"\n'
            'args = ["-m", "link_mcp", "--wiki", "/old/wiki"]\n'
            '\n'
            '[profiles.default]\n'
            'model = "gpt-5"\n'
        )
        replacement = (
            '[mcp_servers.link]\n'
            'command = "/Users/g/.link-mcp-venv/bin/python"\n'
            'args = ["-m", "link_mcp", "--wiki", "/Users/g/link/wiki"]\n'
        )

        updated = pattern.sub(replacement, existing_config)

        self.assertIn('command = "/Users/g/.link-mcp-venv/bin/python"', updated)
        self.assertNotIn("/old/wiki", updated)
        self.assertIn("[profiles.default]", updated)


if __name__ == "__main__":
    unittest.main()
