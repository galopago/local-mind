import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp_package.link_core.capture import (
    capture_filename,
    capture_inbox,
    capture_notes_from_markdown,
    capture_records,
    capture_review_summary,
    capture_title,
    mcp_capture_commands,
    render_accept_capture_text,
    render_capture_inbox_text,
    render_delete_capture_text,
    render_redact_capture_text,
    resolve_capture_file,
)


class CaptureCoreTests(unittest.TestCase):
    def test_capture_title_uses_explicit_title_first(self):
        self.assertEqual(
            capture_title("ignored", "inline", "  Sprint   planning notes  "),
            "Sprint planning notes",
        )

    def test_capture_title_supports_cli_path_sources(self):
        self.assertEqual(
            capture_title("", "raw/first-memory.md", path_source=True),
            "Memory capture: First Memory",
        )

    def test_capture_title_supports_mcp_source_labels(self):
        self.assertEqual(
            capture_title("", "daily standup", default_source="mcp"),
            "Memory capture: daily standup",
        )

    def test_capture_title_falls_back_to_first_note_line(self):
        self.assertEqual(
            capture_title("\n\nRemember that Link is local agent memory.\nMore detail."),
            "Memory capture: Remember that Link is local agent memory",
        )

    def test_capture_filename_is_unique_and_slugged(self):
        root = Path(tempfile.mkdtemp(prefix="link-capture-filename-"))
        first = capture_filename("2026-05-06T01:02:03Z", "Memory capture: First Memory", root)
        first.write_text("# first\n", encoding="utf-8")
        second = capture_filename("2026-05-06T01:02:03Z", "Memory capture: First Memory", root)

        self.assertEqual(first.name, "20260506T010203Z-first-memory.md")
        self.assertEqual(second.name, "20260506T010203Z-first-memory-2.md")

    def test_resolve_capture_file_accepts_supported_root_relative_forms(self):
        root = Path(tempfile.mkdtemp(prefix="link-capture-core-"))
        capture_dir = root / "raw" / "memory-captures"
        capture_dir.mkdir(parents=True)
        capture = capture_dir / "session.md"
        capture.write_text("# Session\n", encoding="utf-8")

        self.assertEqual(resolve_capture_file(root, "raw/memory-captures/session.md"), capture.resolve())
        self.assertEqual(resolve_capture_file(root, "session.md"), capture.resolve())
        self.assertEqual(resolve_capture_file(root, "session"), capture.resolve())

    def test_resolve_capture_file_rejects_paths_outside_root(self):
        root = Path(tempfile.mkdtemp(prefix="link-capture-core-"))
        outside = Path(tempfile.mkdtemp(prefix="link-capture-outside-")) / "session.md"
        outside.write_text("# Outside\n", encoding="utf-8")
        capture_dir = root / "raw" / "memory-captures"
        capture_dir.mkdir(parents=True)
        symlink = capture_dir / "outside.md"
        try:
            symlink.symlink_to(outside)
        except OSError:
            symlink = None

        self.assertIsNone(resolve_capture_file(root, str(outside)))
        self.assertIsNone(resolve_capture_file(root, "../session.md"))
        if symlink is not None:
            self.assertIsNone(resolve_capture_file(root, "outside.md"))

    def test_capture_notes_from_markdown_extracts_notes_section(self):
        meta, notes = capture_notes_from_markdown(
            "---\ntitle: Session\nproject: link\n---\n\n"
            "# Session\n\n"
            "Intro should not be used.\n\n"
            "## Notes\n\n"
            "Important memory candidate.\n\n"
            "## Proposals\n\n"
            "- Ignore generated proposals.\n"
        )

        self.assertEqual(meta["title"], "Session")
        self.assertEqual(meta["project"], "link")
        self.assertEqual(notes, "Important memory candidate.")

    def test_capture_records_redact_snippets_and_filter_project(self):
        root = Path(tempfile.mkdtemp(prefix="link-capture-core-"))
        capture_dir = root / "raw" / "memory-captures"
        capture_dir.mkdir(parents=True)
        fake_key = "sk-" + "a" * 48
        (capture_dir / "alpha.md").write_text(
            "---\n"
            "title: Alpha\n"
            "project: alpha\n"
            "date_captured: 2026-05-05T00:00:00Z\n"
            "---\n\n"
            "# Alpha\n\n"
            "## Notes\n\n"
            f"Remember alpha. Secret {fake_key}\n",
            encoding="utf-8",
        )
        (capture_dir / "beta.md").write_text(
            "---\n"
            "title: Beta\n"
            "project: beta\n"
            "date_captured: 2026-05-04T00:00:00Z\n"
            "---\n\n"
            "# Beta\n\n"
            "## Notes\n\n"
            "Remember beta.\n",
            encoding="utf-8",
        )

        records = capture_records(root, project="alpha", commands_for=mcp_capture_commands)
        inbox = capture_inbox(root, project="alpha", commands_for=mcp_capture_commands)

        self.assertEqual([record["title"] for record in records], ["Alpha"])
        self.assertEqual(records[0]["secret_warnings"], ["OpenAI API key"])
        self.assertIn("[redacted-secret]", records[0]["snippet"])
        self.assertNotIn(fake_key, records[0]["snippet"])
        self.assertIn("accept_capture", records[0]["commands"]["accept"])
        self.assertEqual(inbox["count"], 1)
        self.assertEqual(inbox["warning_count"], 1)
        self.assertEqual(inbox["project"], "alpha")

    def test_capture_inbox_reports_unreadable_captures(self):
        root = Path(tempfile.mkdtemp(prefix="link-capture-core-"))
        capture_dir = root / "raw" / "memory-captures"
        capture_dir.mkdir(parents=True)
        (capture_dir / "good.md").write_text(
            "---\n"
            "title: Good\n"
            "date_captured: 2026-05-05T00:00:00Z\n"
            "---\n\n"
            "## Notes\n\n"
            "Remember the readable capture.\n",
            encoding="utf-8",
        )
        (capture_dir / "locked.md").write_text(
            "---\n"
            "title: Locked\n"
            "---\n\n"
            "## Notes\n\n"
            "This should report a read warning.\n",
            encoding="utf-8",
        )

        original_read_text = Path.read_text

        def flaky_read_text(path: Path, *args, **kwargs):
            if path.name == "locked.md":
                raise OSError("permission denied")
            return original_read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", flaky_read_text):
            inbox = capture_inbox(root)
            summary = capture_review_summary(root)

        self.assertEqual(inbox["count"], 1)
        self.assertEqual(inbox["read_warning_count"], 1)
        self.assertEqual(
            inbox["read_warnings"],
            [{"capture": "raw/memory-captures/locked.md", "error": "permission denied"}],
        )
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["read_warning_count"], 1)

    def test_render_capture_inbox_text_lists_actions_and_warnings(self):
        payload = {
            "project": "alpha",
            "warning_count": 1,
            "read_warning_count": 1,
            "read_warnings": [{"capture": "raw/memory-captures/locked.md", "error": "permission denied"}],
            "captures": [
                {
                    "title": "Alpha capture",
                    "path": "raw/memory-captures/alpha.md",
                    "project": "alpha",
                    "secret_warnings": ["OpenAI API key"],
                    "commands": {
                        "accept": "python3 link.py accept-capture alpha . --index 1",
                        "redact": "python3 link.py redact-capture alpha .",
                        "delete": "python3 link.py delete-capture alpha . --confirm",
                    },
                }
            ],
        }

        text = render_capture_inbox_text(payload)

        self.assertIn("Raw capture inbox", text)
        self.assertIn("Project: alpha", text)
        self.assertIn("1 readable capture · 1 with secret-looking warnings · 1 read warnings", text)
        self.assertIn("raw/memory-captures/locked.md: permission denied", text)
        self.assertIn("1. Alpha capture", text)
        self.assertIn("Secret-looking values: OpenAI API key", text)
        self.assertIn("Accept: python3 link.py accept-capture", text)
        self.assertIn("Redact: python3 link.py redact-capture", text)

    def test_render_accept_capture_text_reports_success_and_rejection(self):
        code, text = render_accept_capture_text({
            "accepted": True,
            "capture": "raw/memory-captures/alpha.md",
            "proposal_index": 1,
            "result": {
                "path": "wiki/memories/prefer-local-memory.md",
                "name": "prefer-local-memory",
                "project": "link",
            },
        })

        self.assertEqual(code, 0)
        self.assertIn("Capture proposal accepted", text)
        self.assertIn("Memory: wiki/memories/prefer-local-memory.md", text)
        self.assertIn('python3 link.py review-memory "prefer-local-memory" .', text)

        code, text = render_accept_capture_text({
            "accepted": False,
            "result": {
                "duplicate_candidates": [{
                    "title": "Prefer local memory",
                    "path": "wiki/memories/prefer-local-memory.md",
                }]
            },
        })

        self.assertEqual(code, 1)
        self.assertIn("Duplicate candidate: Prefer local memory", text)

    def test_render_redact_and_delete_capture_text(self):
        text = render_redact_capture_text({
            "redacted": True,
            "path": "raw/memory-captures/alpha.md",
            "labels": ["OpenAI API key"],
            "replacement_count": 2,
        })

        self.assertIn("Capture redacted", text)
        self.assertIn("Labels: OpenAI API key", text)
        self.assertIn("Replacement count: 2", text)

        text = render_redact_capture_text({
            "redacted": False,
            "path": "raw/memory-captures/alpha.md",
        })
        self.assertIn("No secret-looking values found.", text)

        code, text = render_delete_capture_text({
            "deleted": False,
            "path": "raw/memory-captures/alpha.md",
            "confirmation_required": True,
        })
        self.assertEqual(code, 1)
        self.assertIn("--confirm", text)

        code, text = render_delete_capture_text({
            "deleted": True,
            "path": "raw/memory-captures/alpha.md",
            "confirmation_required": False,
        })
        self.assertEqual(code, 0)
        self.assertIn("Capture deleted", text)


if __name__ == "__main__":
    unittest.main()
