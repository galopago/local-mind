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

    def test_agent_contract_requires_query_validate_and_brief_terms(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-agent-contract-test-"))
        good = tmp / "good.md"
        bad = tmp / "bad.md"
        good.write_text("Use query_link, validate_wiki, and memory_brief.\n", encoding="utf-8")
        bad.write_text("Use query_link only.\n", encoding="utf-8")
        findings: list[str] = []

        release_hygiene.check_agent_contract(
            findings,
            {
                good: ("query_link", "validate_wiki", "memory_brief"),
                bad: ("query_link", "validate_wiki", "memory_brief"),
                tmp / "missing.md": ("query_link",),
            },
        )

        self.assertIn(f"agent contract missing 'validate_wiki' in {bad}", findings)
        self.assertIn(f"agent contract missing 'memory_brief' in {bad}", findings)
        self.assertIn(f"agent contract file missing: {tmp / 'missing.md'}", findings)


if __name__ == "__main__":
    unittest.main()
