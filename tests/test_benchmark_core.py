import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.benchmark import benchmark_health, render_benchmark_text  # noqa: E402


class BenchmarkCoreTests(unittest.TestCase):
    def test_benchmark_health_passes_fast_sqlite_search(self):
        payload = {
            "pages": 1200,
            "search_backend": "sqlite-fts",
            "timings": {
                "cache": 0.2,
                "search": 0.01,
                "query": 0.03,
                "graph_summary": 0.01,
                "page_list": 0.01,
                "graph_initial": 0.01,
                "graph": 0.04,
            },
        }

        health = benchmark_health(payload)

        self.assertEqual(health["status"], "pass")
        self.assertEqual(health["label"], "interactive")
        self.assertEqual(health["summary"], "Ready for interactive local agent memory.")
        self.assertEqual(health["warnings"], [])
        self.assertEqual(health["recommendations"], [])

    def test_benchmark_health_warns_on_slow_paths(self):
        payload = {
            "pages": 20,
            "search_backend": "sqlite-fts",
            "timings": {
                "cache": 0.2,
                "search": 1.5,
                "query": 0.03,
                "graph_summary": 0.01,
                "page_list": 0.01,
                "graph_initial": 0.01,
                "graph": 0.04,
            },
        }

        health = benchmark_health(payload)

        self.assertEqual(health["status"], "warn")
        self.assertEqual(health["label"], "review")
        self.assertIn("search took 1.5000s", health["warnings"][0])
        self.assertIn("Review recommended", health["summary"])
        self.assertIn("Run link doctor --fix", health["recommendations"][0])
        self.assertIn("sqlite3/FTS5", health["recommendations"][1])

    def test_benchmark_health_warns_on_large_token_fallback(self):
        payload = {
            "pages": 1000,
            "search_backend": "token-index",
            "timings": {
                "cache": 0.2,
                "search": 0.01,
                "query": 0.03,
                "graph_summary": 0.01,
                "page_list": 0.01,
                "graph_initial": 0.01,
                "graph": 0.04,
            },
        }

        health = benchmark_health(payload)

        self.assertEqual(health["status"], "warn")
        self.assertIn("SQLite FTS", health["warnings"][0])
        self.assertIn("sqlite3/FTS5", health["recommendations"][1])

    def test_benchmark_health_gives_graph_specific_recommendations(self):
        payload = {
            "pages": 2000,
            "search_backend": "sqlite-fts",
            "timings": {
                "cache": 0.2,
                "search": 0.01,
                "query": 0.03,
                "graph_summary": 0.01,
                "page_list": 0.01,
                "graph_initial": 1.4,
                "graph": 2.4,
            },
        }

        health = benchmark_health(payload)

        self.assertEqual(health["status"], "warn")
        self.assertTrue(any("graph_initial took" in warning for warning in health["warnings"]))
        self.assertTrue(any("graph took" in warning for warning in health["warnings"]))
        self.assertIn("focused neighborhoods", " ".join(health["recommendations"]))

    def test_render_benchmark_text_includes_agent_safe_payloads_and_packet(self):
        payload = {
            "target": "/tmp/link",
            "query": "agent memory",
            "project": "link",
            "pages": 12,
            "memories": 1,
            "edges": 58,
            "search_backend": "sqlite-fts",
            "search_results": 4,
            "context_items": 3,
            "found": True,
            "graph_summary": {"returned_nodes": 5, "returned_edges": 6},
            "page_list": {"returned_count": 12},
            "graph_initial": {"mode": "full", "nodes": 12, "total_nodes": 12},
            "health": {
                "label": "interactive",
                "summary": "Ready for interactive local agent memory.",
                "warnings": [],
                "recommendations": [],
            },
            "timings": {
                "cache": 0.1,
                "search": 0.01,
                "query": 0.02,
                "graph_summary": 0.03,
                "page_list": 0.04,
                "graph_initial": 0.05,
                "graph": 0.06,
            },
            "budget_report": {
                "context_packet": {
                    "estimated_chars": 1200,
                    "estimated_tokens": 300,
                    "has_more": False,
                }
            },
        }

        text = render_benchmark_text(payload)

        self.assertIn("Link benchmark: /tmp/link", text)
        self.assertIn("Project: link", text)
        self.assertIn("Agent-safe payloads: graph summary 5 nodes/6 edges · page list 12 pages", text)
        self.assertIn("Graph page initial load: full · 12/12 nodes", text)
        self.assertIn("Verdict: interactive", text)
        self.assertIn("Packet: 1200 chars · 300 tokens · has_more=False", text)
        self.assertIn("Result: found", text)


if __name__ == "__main__":
    unittest.main()
