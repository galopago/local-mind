import unittest

from mcp_package.link_core.cli_memory import (
    render_forget_memory_text,
    render_memory_status_text,
    render_recall_text,
    render_review_memory_text,
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

    def test_render_memory_status_archive(self):
        code, text = render_memory_status_text({
            "updated": True,
            "name": "prefer-local-memory",
            "title": "Prefer local memory",
            "path": "wiki/memories/prefer-local-memory.md",
            "previous_status": "active",
            "status": "archived",
        }, action="archive")

        self.assertEqual(code, 0)
        self.assertIn("Memory archived", text)
        self.assertIn('Restore: python3 link.py restore-memory "prefer-local-memory" .', text)

    def test_render_memory_status_restore(self):
        code, text = render_memory_status_text({
            "updated": False,
            "name": "prefer-local-memory",
            "title": "Prefer local memory",
            "path": "wiki/memories/prefer-local-memory.md",
            "previous_status": "active",
            "status": "active",
        }, action="restore")

        self.assertEqual(code, 0)
        self.assertIn("Memory already active", text)
        self.assertNotIn("Restore:", text)

    def test_render_forget_memory_requires_confirmation(self):
        code, text = render_forget_memory_text({
            "found": True,
            "confirmation_required": True,
            "name": "prefer-local-memory",
        }, identifier="prefer-local-memory")

        self.assertEqual(code, 1)
        self.assertIn("Confirmation required.", text)
        self.assertIn('--confirm', text)

    def test_render_forget_memory_done(self):
        code, text = render_forget_memory_text({
            "found": True,
            "forgotten": True,
            "title": "Prefer local memory",
            "path": "wiki/memories/prefer-local-memory.md",
            "backlinks_rebuilt": True,
        }, identifier="prefer-local-memory")

        self.assertEqual(code, 0)
        self.assertIn("Memory forgotten", text)
        self.assertIn("Backlinks rebuilt: yes", text)

    def test_render_review_memory_with_remaining_issues(self):
        code, text = render_review_memory_text({
            "updated": True,
            "title": "Prefer local memory",
            "path": "wiki/memories/prefer-local-memory.md",
            "previous_review_status": "pending",
            "review_status": "reviewed",
            "remaining_issue_count": 1,
            "remaining_issues": [{
                "severity": "medium",
                "code": "missing_source",
                "message": "Memory should cite a source.",
            }],
        })

        self.assertEqual(code, 0)
        self.assertIn("Memory reviewed", text)
        self.assertIn("1 issue still need attention:", text)
        self.assertIn("[medium] missing_source: Memory should cite a source.", text)


if __name__ == "__main__":
    unittest.main()
