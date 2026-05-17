import unittest

from mcp_package.link_core.cli_memory import (
    render_recall_text,
    render_remember_text,
    render_update_memory_text,
)


class CliMemoryCoreTests(unittest.TestCase):
    def test_render_remember_created(self):
        code, text = render_remember_text({
            "created": True,
            "title": "Prefer release branches",
            "path": "wiki/memories/prefer-release-branches.md",
            "memory_type": "preference",
            "scope": "project",
            "project": "link",
        })

        self.assertEqual(code, 0)
        self.assertIn("Memory saved", text)
        self.assertIn("Project: link", text)
        self.assertIn('python3 link.py recall "Prefer release branches" .', text)

    def test_render_remember_duplicate(self):
        code, text = render_remember_text({
            "created": False,
            "duplicate": True,
            "title": "Prefer release branches",
            "memory_type": "preference",
            "scope": "project",
            "candidates": [{
                "name": "prefer-release-branches",
                "title": "Prefer release branches",
                "path": "wiki/memories/prefer-release-branches.md",
            }],
        })

        self.assertEqual(code, 0)
        self.assertIn("Similar memory already exists", text)
        self.assertIn("Existing candidates:", text)
        self.assertIn('python3 link.py explain-memory "prefer-release-branches" .', text)

    def test_render_remember_conflict(self):
        code, text = render_remember_text({
            "created": False,
            "conflict": True,
            "title": "Prefer develop branches",
            "memory_type": "preference",
            "scope": "project",
            "conflict_candidates": [{
                "name": "prefer-release-branches",
                "title": "Prefer release branches",
                "path": "wiki/memories/prefer-release-branches.md",
                "conflict_reasons": ["different_branch_policy"],
            }],
        })

        self.assertEqual(code, 0)
        self.assertIn("Possible conflicting memory found", text)
        self.assertIn("Reasons: different_branch_policy", text)

    def test_render_update_memory(self):
        code, text = render_update_memory_text({
            "updated": True,
            "name": "prefer-release-branches",
            "title": "Prefer release branches",
            "path": "wiki/memories/prefer-release-branches.md",
            "update_count": 2,
            "previous_review_status": "reviewed",
            "review_status": "pending",
        })

        self.assertEqual(code, 0)
        self.assertIn("Memory updated", text)
        self.assertIn("Review: reviewed -> pending", text)
        self.assertIn('python3 link.py review-memory "prefer-release-branches" .', text)

    def test_render_recall_empty(self):
        code, text = render_recall_text(query="release branches", results=[], project="link")

        self.assertEqual(code, 0)
        self.assertIn("Link memory recall: release branches", text)
        self.assertIn("Project: link", text)
        self.assertIn("No matching memories found.", text)

    def test_render_recall_results(self):
        code, text = render_recall_text(
            query="release branches",
            include_archived=True,
            results=[{
                "title": "Prefer release branches",
                "memory_type": "preference",
                "scope": "project",
                "path": "wiki/memories/prefer-release-branches.md",
                "recall": {"state": "ready"},
                "tldr": "Use release branches for public changes.",
            }],
        )

        self.assertEqual(code, 0)
        self.assertIn("Including archived/stale memories", text)
        self.assertIn("1 memory", text)
        self.assertIn("Recall: ready", text)
        self.assertIn("Use release branches for public changes.", text)


if __name__ == "__main__":
    unittest.main()
