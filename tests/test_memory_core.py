import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.memory import memory_inbox, memory_profile, memory_records, propose_memories_from_text, recall_memories  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
