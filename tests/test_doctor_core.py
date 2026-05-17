import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.doctor import (  # noqa: E402
    DoctorReport,
    doctor_validation_errors,
    find_dead_links,
    find_isolated_pages,
    find_pages_missing_source_sections,
    find_pages_missing_summaries,
    find_source_count_mismatches,
    find_unindexed_pages,
    format_validation_error_summary,
    join_limited,
    render_doctor_report,
    source_section_links,
)


class DoctorCoreTests(unittest.TestCase):
    def test_render_healthy_report_with_fixes_and_warnings(self):
        report = DoctorReport("/tmp/link", fix_requested=True)
        report.fixes.append("rebuilt wiki/index.md")
        report.add_ok("OK required wiki structure")
        report.add_warning("memories need review: example")

        text = render_doctor_report(report)

        self.assertIn("Link doctor: /tmp/link", text)
        self.assertIn("Fixes applied:\n- rebuilt wiki/index.md", text)
        self.assertIn("OK required wiki structure", text)
        self.assertIn("Warnings:\n- memories need review: example", text)
        self.assertIn("Result: healthy", text)

    def test_render_error_report(self):
        report = DoctorReport("/tmp/link")
        report.add_error("dead wikilinks: a -> b")

        text = render_doctor_report(report)

        self.assertFalse(report.healthy)
        self.assertIn("Errors:\n- dead wikilinks: a -> b", text)
        self.assertIn("Result: needs attention", text)

    def test_validation_errors_are_filtered_to_doctor_codes(self):
        payload = {
            "findings": [
                {"severity": "error", "code": "missing_required_section", "path": "sources/a.md", "message": "bad"},
                {"severity": "error", "code": "dead_wikilink", "path": "concepts/b.md", "message": "missing"},
                {"severity": "warning", "code": "missing_summary", "path": "sources/c.md", "message": "warn"},
            ]
        }

        findings = doctor_validation_errors(payload)
        summary = format_validation_error_summary(findings)

        self.assertEqual(len(findings), 1)
        self.assertIn("sources/a.md [missing_required_section] bad", summary)
        self.assertNotIn("dead_wikilink", summary)

    def test_join_limited_caps_items(self):
        text = join_limited("items: ", [str(index) for index in range(10)], limit=3)

        self.assertEqual(text, "items: 0, 1, 2")

    def test_page_health_helpers_find_doctor_findings(self):
        root = Path(tempfile.mkdtemp(prefix="link-doctor-core-"))
        wiki = root / "wiki"
        (wiki / "concepts").mkdir(parents=True)
        (wiki / "sources").mkdir()
        (wiki / "index.md").write_text("# Index\n\n[[agent-memory]]\n", encoding="utf-8")
        (wiki / "log.md").write_text("# Log\n", encoding="utf-8")
        (wiki / "concepts" / "agent-memory.md").write_text(
            "---\n"
            "type: concept\n"
            "title: Agent Memory\n"
            "source_count: 2\n"
            "---\n"
            "# Agent Memory\n\n"
            "> **TLDR:** Durable context.\n\n"
            "Links to [[missing-page]].\n\n"
            "## Sources\n\n"
            "- [[source-one]]\n",
            encoding="utf-8",
        )
        (wiki / "concepts" / "orphan.md").write_text(
            "---\ntype: concept\ntitle: Orphan\n---\n# Orphan\n\nNo summary.\n",
            encoding="utf-8",
        )
        (wiki / "concepts" / "no-sources.md").write_text(
            "---\ntype: concept\ntitle: No Sources\n---\n# No Sources\n\n> **TLDR:** Missing sources.\n",
            encoding="utf-8",
        )
        (wiki / "sources" / "source-one.md").write_text(
            "---\ntype: source\ntitle: Source One\n---\n# Source One\n\n> **TLDR:** Source.\n\n[[agent-memory]]\n",
            encoding="utf-8",
        )

        self.assertEqual(find_dead_links(wiki), ["agent-memory -> missing-page"])
        self.assertEqual(find_unindexed_pages(wiki), ["no-sources", "orphan", "source-one"])
        self.assertEqual(find_pages_missing_summaries(wiki), ["concepts/orphan.md"])
        self.assertEqual(find_pages_missing_source_sections(wiki), ["concepts/no-sources.md", "concepts/orphan.md"])
        self.assertEqual(find_source_count_mismatches(wiki), ["concepts/agent-memory.md source_count=2, sources section has 1"])
        self.assertEqual(find_isolated_pages(wiki), ["concepts/no-sources.md", "concepts/orphan.md"])

    def test_source_section_links_reads_only_sources_section(self):
        links = source_section_links("Intro [[outside]]\n\n## Sources\n\n- [[inside]]\n\n## Next\n\n[[later]]")

        self.assertEqual(links, {"inside"})


if __name__ == "__main__":
    unittest.main()
