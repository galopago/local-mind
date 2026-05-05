import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.memory import (  # noqa: E402
    mark_memory_reviewed,
    memory_inbox,
    memory_log_entries,
    memory_profile,
    memory_records,
    propose_memories_from_text,
    recall_memories,
    recall_state,
    resolve_memory_page,
    set_memory_status,
    update_memory_page,
)


class MemoryCoreTests(unittest.TestCase):
    def test_memory_records_profile_and_recall(self):
        root = Path(tempfile.mkdtemp(prefix="link-memory-core-"))
        wiki = root / "wiki"
        memories = wiki / "memories"
        memories.mkdir(parents=True)
        (memories / "prefer-release-branches.md").write_text(
            "---\n"
            "type: memory\n"
            "title: \"Prefer release branches\"\n"
            "memory_type: preference\n"
            "scope: project\n"
            "status: active\n"
            "date_captured: \"2026-05-05T00:00:00Z\"\n"
            "source: \"unit test\"\n"
            "review_status: reviewed\n"
            "tags: [memory, release, workflow]\n"
            "---\n\n"
            "# Prefer release branches\n\n"
            "> **TLDR:** User prefers release branches for Link work.\n\n"
            "## Memory\n\nUser prefers release branches for Link work.\n",
            encoding="utf-8",
        )
        (memories / "old-branch-rule.md").write_text(
            "---\n"
            "type: memory\n"
            "title: \"Old branch rule\"\n"
            "memory_type: preference\n"
            "scope: project\n"
            "status: archived\n"
            "date_captured: \"2026-05-04T00:00:00Z\"\n"
            "source: \"unit test\"\n"
            "review_status: reviewed\n"
            "tags: [memory, archive]\n"
            "---\n\n"
            "# Old branch rule\n\n"
            "> **TLDR:** User previously used direct main pushes.\n",
            encoding="utf-8",
        )

        records = memory_records(wiki)
        profile = memory_profile(records)
        inbox = memory_inbox(records)
        recalled = recall_memories(records, "release branches")

        self.assertEqual(len(records), 2)
        self.assertIn("body", records[0])
        self.assertEqual(profile["memory_count"], 2)
        self.assertEqual(profile["active_count"], 1)
        self.assertEqual(profile["archived"][0]["name"], "old-branch-rule")
        self.assertEqual(inbox["review_count"], 0)
        self.assertEqual(recalled[0]["name"], "prefer-release-branches")
        self.assertNotIn("body", recalled[0])

    def test_proposals_are_duplicate_aware_and_write_free(self):
        records = [
            {
                "name": "prefer-release-branches",
                "path": "wiki/memories/prefer-release-branches.md",
                "title": "Prefer release branches",
                "memory_type": "preference",
                "scope": "project",
                "status": "active",
                "tldr": "User prefers release branches for Link work.",
                "snippet": "User prefers release branches for Link work.",
                "body": "User prefers release branches for Link work.",
            }
        ]

        payload = propose_memories_from_text(
            "\n".join([
                "- I prefer release branches for Link work.",
                "- We decided to keep Memory Mode local and source-backed.",
                "- Maybe we could add cloud sync later.",
            ]),
            records,
            source="unit test",
        )

        self.assertTrue(payload["proposed"])
        self.assertFalse(payload["writes_memory"])
        self.assertEqual(payload["count"], 2)
        self.assertGreaterEqual(payload["skipped_count"], 1)
        self.assertEqual(payload["proposals"][0]["suggested_action"], "update-memory")
        duplicate = payload["proposals"][0]["duplicate_candidates"][0]
        self.assertEqual(duplicate["name"], "prefer-release-branches")
        self.assertNotIn("body", duplicate)
        self.assertEqual(payload["proposals"][1]["memory_type"], "decision")

    def test_memory_resolution_logs_and_recall_state(self):
        root = Path(tempfile.mkdtemp(prefix="link-memory-resolution-"))
        wiki = root / "wiki"
        memories = wiki / "memories"
        memories.mkdir(parents=True)
        (memories / "prefer-focused-commits.md").write_text(
            "---\n"
            "type: memory\n"
            "title: \"Prefer focused commits\"\n"
            "memory_type: preference\n"
            "scope: project\n"
            "status: active\n"
            "date_captured: \"2026-05-05T00:00:00Z\"\n"
            "source: \"unit test\"\n"
            "review_status: reviewed\n"
            "tags: [memory, git]\n"
            "---\n\n"
            "# Prefer focused commits\n\n"
            "> **TLDR:** User prefers focused commits on develop.\n\n"
            "## Memory\n\nUser prefers focused commits on develop.\n",
            encoding="utf-8",
        )
        (memories / "duplicate-a.md").write_text(
            "---\n"
            "title: \"Duplicate title\"\n"
            "memory_type: note\n"
            "scope: project\n"
            "status: active\n"
            "date_captured: \"2026-05-05T00:00:00Z\"\n"
            "source: \"unit test\"\n"
            "review_status: reviewed\n"
            "---\n\n"
            "# Duplicate title\n",
            encoding="utf-8",
        )
        (memories / "duplicate-b.md").write_text(
            "---\n"
            "title: \"Duplicate title\"\n"
            "memory_type: note\n"
            "scope: project\n"
            "status: active\n"
            "date_captured: \"2026-05-05T00:00:00Z\"\n"
            "source: \"unit test\"\n"
            "review_status: reviewed\n"
            "---\n\n"
            "# Duplicate title\n",
            encoding="utf-8",
        )
        (wiki / "log.md").write_text(
            "# Link Wiki Log\n\n"
            "## unrelated\n\n- No match\n"
            "---\n"
            "## remember | Prefer focused commits\n\n"
            "- Added [[prefer-focused-commits]]\n"
            "---\n"
            "## update | wiki/memories/prefer-focused-commits.md\n\n"
            "- Updated memory text\n"
            "---\n",
            encoding="utf-8",
        )

        path, record, error = resolve_memory_page(wiki, "Prefer focused commits")
        self.assertIsNone(error)
        self.assertEqual(path, (memories / "prefer-focused-commits.md").resolve())
        self.assertEqual(record["name"], "prefer-focused-commits")
        self.assertIn("body", record)

        path, record, error = resolve_memory_page(wiki, "wiki/memories/prefer-focused-commits.md")
        self.assertIsNone(error)
        self.assertEqual(path, (memories / "prefer-focused-commits.md").resolve())
        self.assertEqual(record["title"], "Prefer focused commits")

        path, record, error = resolve_memory_page(wiki, "../log.md")
        self.assertIsNone(path)
        self.assertIsNone(record)
        self.assertEqual(error, "memory not found: ../log.md")

        path, record, error = resolve_memory_page(wiki, "Duplicate title")
        self.assertIsNone(path)
        self.assertIsNone(record)
        self.assertIn("ambiguous", error)

        entries = memory_log_entries(wiki, {"name": "prefer-focused-commits", "title": "Prefer focused commits"}, limit=1)
        self.assertEqual(len(entries), 1)
        self.assertIn("wiki/memories/prefer-focused-commits.md", entries[0])

        ready = recall_state(record={"status": "active"}, issues=[])
        needs_review = recall_state(record={"status": "active"}, issues=[{"severity": "medium"}])
        unsafe = recall_state(record={"status": "active"}, issues=[{"severity": "high"}])
        disabled = recall_state(record={"status": "archived"}, issues=[])
        self.assertEqual(ready["state"], "ready")
        self.assertEqual(needs_review["state"], "needs_review")
        self.assertEqual(unsafe["state"], "unsafe")
        self.assertEqual(disabled["state"], "disabled")

    def test_memory_lifecycle_mutations_update_files_and_callbacks(self):
        root = Path(tempfile.mkdtemp(prefix="link-memory-lifecycle-"))
        wiki = root / "wiki"
        memories = wiki / "memories"
        memories.mkdir(parents=True)
        memory_path = memories / "prefer-focused-commits.md"
        memory_path.write_text(
            "---\n"
            "type: memory\n"
            "title: \"Prefer focused commits\"\n"
            "memory_type: preference\n"
            "scope: project\n"
            "status: active\n"
            "date_captured: \"2026-05-05T00:00:00Z\"\n"
            "source: \"unit test\"\n"
            "review_status: pending\n"
            "tags: [memory, git]\n"
            "---\n\n"
            "# Prefer focused commits\n\n"
            "> **TLDR:** User prefers focused commits on develop.\n\n"
            "## Memory\n\nUser prefers focused commits on develop.\n",
            encoding="utf-8",
        )
        logged: list[tuple[str, str, str, list[str]]] = []
        rebuilds = []

        def log_writer(timestamp: str, operation: str, description: str, lines: list[str]) -> None:
            logged.append((timestamp, operation, description, lines))

        reviewed = mark_memory_reviewed(
            wiki,
            "prefer-focused-commits",
            note="confirmed",
            timestamp="2026-05-05T01:00:00Z",
            records=memory_records(wiki),
            log_writer=log_writer,
        )
        reviewed_text = memory_path.read_text(encoding="utf-8")

        self.assertTrue(reviewed["updated"])
        self.assertEqual(reviewed["review_status"], "reviewed")
        self.assertEqual(reviewed["remaining_issue_count"], 0)
        self.assertIn("review_status: reviewed", reviewed_text)
        self.assertIn('review_note: "confirmed"', reviewed_text)
        self.assertEqual(logged[-1][1], "review-memory")

        updated = update_memory_page(
            wiki,
            "Prefer focused commits",
            "Also prefer one logical change per commit.",
            source="unit test",
            timestamp="2026-05-05T02:00:00Z",
            records=memory_records(wiki),
            log_writer=log_writer,
            rebuild_backlinks=lambda: rebuilds.append(True) or True,
        )
        updated_text = memory_path.read_text(encoding="utf-8")

        self.assertTrue(updated["updated"])
        self.assertEqual(updated["previous_review_status"], "reviewed")
        self.assertEqual(updated["review_status"], "pending")
        self.assertEqual(updated["update_count"], 1)
        self.assertTrue(updated["backlinks_rebuilt"])
        self.assertEqual(rebuilds, [True])
        self.assertIn("updated_at:", updated_text)
        self.assertIn("update_count: 1", updated_text)
        self.assertIn('last_update_source: "unit test"', updated_text)
        self.assertNotIn("reviewed_at:", updated_text)
        self.assertIn("Also prefer one logical change per commit.", updated_text)
        self.assertEqual(logged[-1][1], "update-memory")

        archived = set_memory_status(
            wiki,
            "prefer-focused-commits",
            "archived",
            reason="stale",
            timestamp="2026-05-05T03:00:00Z",
            records=memory_records(wiki),
            log_writer=log_writer,
        )
        archived_text = memory_path.read_text(encoding="utf-8")

        self.assertTrue(archived["updated"])
        self.assertEqual(archived["status"], "archived")
        self.assertIn("status: archived", archived_text)
        self.assertIn("archived_at:", archived_text)
        self.assertIn('archive_reason: "stale"', archived_text)
        self.assertEqual(logged[-1][1], "archive-memory")

        with self.assertRaisesRegex(ValueError, "restore it first"):
            update_memory_page(
                wiki,
                "prefer-focused-commits",
                "Should not write while archived.",
                source="unit test",
                timestamp="2026-05-05T04:00:00Z",
                records=memory_records(wiki),
            )

        restored = set_memory_status(
            wiki,
            "prefer-focused-commits",
            "active",
            reason=None,
            timestamp="2026-05-05T05:00:00Z",
            records=memory_records(wiki),
            log_writer=log_writer,
        )
        restored_text = memory_path.read_text(encoding="utf-8")

        self.assertTrue(restored["updated"])
        self.assertEqual(restored["status"], "active")
        self.assertIn("status: active", restored_text)
        self.assertIn("restored_at:", restored_text)
        self.assertNotIn("archived_at:", restored_text)
        self.assertNotIn("archive_reason:", restored_text)
        self.assertEqual(logged[-1][1], "restore-memory")


if __name__ == "__main__":
    unittest.main()
