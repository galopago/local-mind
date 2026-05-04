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


if __name__ == "__main__":
    unittest.main()
