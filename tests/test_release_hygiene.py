import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "release_hygiene", ROOT / "scripts/check_release_hygiene.py"
)
release_hygiene = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(release_hygiene)


class ReleaseHygieneTests(unittest.TestCase):
    def test_read_changelog_versions(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-changelog-test-"))
        changelog = tmp / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [Unreleased]\n\n## [1.0.5] - 2026-05-02\n",
            encoding="utf-8",
        )

        self.assertEqual(
            release_hygiene.read_changelog_versions(changelog),
            ["Unreleased", "1.0.5"],
        )

    def test_changelog_requires_unreleased_and_current_version(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-changelog-test-"))
        changelog = tmp / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [1.0.4] - 2026-05-02\n", encoding="utf-8")
        findings: list[str] = []

        release_hygiene.check_changelog(findings, "1.0.5", changelog)

        self.assertIn("CHANGELOG.md missing ## [Unreleased] section", findings)
        self.assertIn("CHANGELOG.md missing current package version: 1.0.5", findings)

    def test_changelog_accepts_current_version(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-changelog-test-"))
        changelog = tmp / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [Unreleased]\n\n## [1.0.5] - 2026-05-02\n",
            encoding="utf-8",
        )
        findings: list[str] = []

        release_hygiene.check_changelog(findings, "1.0.5", changelog)

        self.assertEqual(findings, [])

    def test_version_values_require_server_package_version(self):
        findings: list[str] = []

        release_hygiene.check_version_values(
            findings,
            {
                "mcp_package/pyproject.toml": "1.0.5",
                "mcp_package/link_mcp/__init__.py": "1.0.5",
                "mcp_package/link_core/version.py": "1.0.5",
                "mcp_package/server.json": "1.0.5",
            },
            set(),
        )

        self.assertIn("version mismatch: server.json has no link-mcp package version", findings)

    def test_version_values_accept_matching_release_files(self):
        findings: list[str] = []

        release_hygiene.check_version_values(
            findings,
            {
                "mcp_package/pyproject.toml": "1.0.5",
                "mcp_package/link_mcp/__init__.py": "1.0.5",
                "mcp_package/link_core/version.py": "1.0.5",
                "mcp_package/server.json": "1.0.5",
            },
            {"1.0.5"},
        )

        self.assertEqual(findings, [])

    def test_version_values_report_mismatched_package_version(self):
        findings: list[str] = []

        release_hygiene.check_version_values(
            findings,
            {
                "mcp_package/pyproject.toml": "1.0.5",
                "mcp_package/link_mcp/__init__.py": "1.0.5",
                "mcp_package/link_core/version.py": "1.0.5",
                "mcp_package/server.json": "1.0.5",
            },
            {"1.0.4"},
        )

        self.assertIn("version mismatch: mcp_package/pyproject.toml is '1.0.5'", findings)
        self.assertIn("version mismatch: server.json package versions are ['1.0.4']", findings)

    def test_agent_contract_requires_core_public_workflow_terms(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-agent-contract-test-"))
        good = tmp / "good.md"
        bad = tmp / "bad.md"
        required_terms = (
            "link_status",
            "starter_prompts",
            "ingest_status",
            "query_link",
            "memory_brief",
            "get_graph_summary",
            "backup_wiki",
            "validate_wiki",
        )
        good.write_text(
            "Use link_status, starter_prompts, ingest_status, query_link, "
            "memory_brief, get_graph_summary, backup_wiki, and validate_wiki.\n",
            encoding="utf-8",
        )
        bad.write_text("Use query_link only.\n", encoding="utf-8")
        findings: list[str] = []

        release_hygiene.check_agent_contract(
            findings,
            {
                good: required_terms,
                bad: required_terms,
                tmp / "missing.md": ("query_link",),
            },
        )

        self.assertIn(f"agent contract missing 'link_status' in {bad}", findings)
        self.assertIn(f"agent contract missing 'starter_prompts' in {bad}", findings)
        self.assertIn(f"agent contract missing 'ingest_status' in {bad}", findings)
        self.assertIn(f"agent contract missing 'get_graph_summary' in {bad}", findings)
        self.assertIn(f"agent contract missing 'backup_wiki' in {bad}", findings)
        self.assertIn(f"agent contract missing 'validate_wiki' in {bad}", findings)
        self.assertIn(f"agent contract missing 'memory_brief' in {bad}", findings)
        self.assertIn(f"agent contract file missing: {tmp / 'missing.md'}", findings)

    def test_tracked_path_hygiene_blocks_build_artifacts_and_secret_names(self):
        findings: list[str] = []

        skip_wheel = release_hygiene.check_tracked_path_hygiene(
            findings,
            Path("mcp_package/dist/link_mcp-1.2.0-py3-none-any.whl"),
        )
        skip_secret = release_hygiene.check_tracked_path_hygiene(findings, Path(".pypirc"))
        skip_normal = release_hygiene.check_tracked_path_hygiene(findings, Path("README.md"))

        self.assertTrue(skip_wheel)
        self.assertTrue(skip_secret)
        self.assertFalse(skip_normal)
        self.assertIn(
            "build artifact should not be tracked: mcp_package/dist/link_mcp-1.2.0-py3-none-any.whl",
            findings,
        )
        self.assertIn("sensitive-looking tracked filename: .pypirc", findings)

    def test_outbound_network_hygiene_blocks_runtime_http_clients(self):
        findings: list[str] = []

        release_hygiene.check_outbound_network_hygiene(
            findings,
            Path("mcp_package/link_core/example.py"),
            "import requests\nrequests.get('https://example.com')\n",
        )
        release_hygiene.check_outbound_network_hygiene(
            findings,
            Path("integrations/example/install.sh"),
            "curl https://example.com/install.sh\n",
        )
        release_hygiene.check_outbound_network_hygiene(
            findings,
            Path("mcp_package/link_core/stdlib.py"),
            "import http.client\n",
        )
        release_hygiene.check_outbound_network_hygiene(
            findings,
            Path("mcp_package/link_core/urllib_alias.py"),
            "from urllib import request\n",
        )
        release_hygiene.check_outbound_network_hygiene(
            findings,
            Path("mcp_package/link_core/socket_client.py"),
            "import socket\n",
        )
        release_hygiene.check_outbound_network_hygiene(
            findings,
            Path("README.md"),
            "https://example.com is allowed in docs.\n",
        )
        release_hygiene.check_outbound_network_hygiene(
            findings,
            Path("scripts/smoke_http_viewer.py"),
            "import socket\nimport urllib.request\n",
        )

        self.assertIn("outbound network code in mcp_package/link_core/example.py: requests import", findings)
        self.assertIn("outbound network code in integrations/example/install.sh: curl command", findings)
        self.assertIn("outbound network code in mcp_package/link_core/stdlib.py: http.client import", findings)
        self.assertIn("outbound network code in mcp_package/link_core/urllib_alias.py: urllib request import", findings)
        self.assertIn("outbound network code in mcp_package/link_core/socket_client.py: socket import", findings)
        self.assertEqual(len(findings), 5)


if __name__ == "__main__":
    unittest.main()
