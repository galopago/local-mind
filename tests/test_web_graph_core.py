import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.web_graph import (  # noqa: E402
    GRAPH_CATEGORY_COLORS,
    graph_category_options,
    graph_initial_payload,
    graph_legend_items,
    graph_needs_bounded_overview,
)


class WebGraphCoreTests(unittest.TestCase):
    def test_graph_initial_payload_uses_full_graph_under_limit(self):
        graph = {
            "nodes": [
                {"id": "root", "category": "root"},
                {"id": "a", "title": "A", "category": "concepts"},
                {"id": "b", "title": "B", "category": "sources"},
            ],
            "edges": [
                {"source": "a", "target": "b"},
                {"source": "root", "target": "a"},
            ],
        }

        payload = graph_initial_payload(graph, full_node_limit=10)

        self.assertEqual(payload["graph_mode"], "full")
        self.assertEqual(payload["node_count"], 2)
        self.assertEqual(payload["edge_count"], 1)
        self.assertEqual(payload["total_node_count"], 2)
        self.assertEqual(payload["total_edge_count"], 1)

    def test_graph_initial_payload_uses_summary_for_large_graph(self):
        full_graph = {
            "nodes": [{"id": f"n-{index}", "category": "concepts"} for index in range(5)],
            "edges": [{"source": "n-0", "target": "n-1"}],
        }
        summary_graph = {
            "nodes": [{"id": "n-0", "category": "concepts"}, {"id": "n-1", "category": "concepts"}],
            "edges": [{"source": "n-0", "target": "n-1"}],
        }

        payload = graph_initial_payload(full_graph, summary_graph=summary_graph, full_node_limit=2)

        self.assertEqual(payload["graph_mode"], "summary")
        self.assertEqual(payload["node_count"], 2)
        self.assertEqual(payload["edge_count"], 1)
        self.assertEqual(payload["total_node_count"], 5)
        self.assertIn("fast overview", payload["graph_note"])
        self.assertTrue(graph_needs_bounded_overview(full_graph, full_node_limit=2))

    def test_graph_category_options_and_legend_escape_content(self):
        nodes = [
            {"id": "a", "category": "concepts"},
            {"id": "b", "category": 'weird"type'},
            {"id": "root", "category": "root"},
        ]

        options = graph_category_options(nodes)
        legend = graph_legend_items({**GRAPH_CATEGORY_COLORS, "<bad>": '"red"'})

        self.assertIn('<option value="concepts">concepts</option>', options)
        self.assertIn('<option value="weird&quot;type">weird&quot;type</option>', options)
        self.assertNotIn(">root<", options)
        self.assertIn("&lt;bad&gt;", legend)
        self.assertIn("&quot;red&quot;", legend)


if __name__ == "__main__":
    unittest.main()
