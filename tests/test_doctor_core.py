import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.doctor import (  # noqa: E402
    DoctorReport,
    doctor_validation_errors,
    format_validation_error_summary,
    join_limited,
    render_doctor_report,
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


if __name__ == "__main__":
    unittest.main()
