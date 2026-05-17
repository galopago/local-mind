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
    render_graph_empty_body,
    render_graph_page_body,
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

    def test_render_graph_empty_body(self):
        html = render_graph_empty_body()

        self.assertIn("Knowledge Graph", html)
        self.assertIn("No graph pages yet.", html)
        self.assertNotIn('id="graph-canvas"', html)

    def test_render_graph_page_body_includes_controls_and_escapes_note(self):
        html = render_graph_page_body(
            graph_js="<script>var resetButton = true;</script>",
            node_count=3,
            edge_count=2,
            total_node_count=10,
            total_edge_count=20,
            graph_mode="summary",
            graph_note=' <fast & "bounded">',
            category_options='<option value="concepts">concepts</option>',
            legend_items="<span></span>concepts",
        )

        self.assertIn('id="graph-reset"', html)
        self.assertIn('id="graph-labels"', html)
        self.assertIn('id="graph-motion"', html)
        self.assertIn('id="graph-fullscreen"', html)
        self.assertIn("Load graph data (10 nodes)", html)
        self.assertIn('id="graph-search"', html)
        self.assertIn('id="graph-category"', html)
        self.assertIn('<option value="concepts">concepts</option>', html)
        self.assertIn('id="graph-depth"', html)
        self.assertIn('id="graph-status"', html)
        self.assertIn("3/10 nodes · 2/20 edges", html)
        self.assertIn('role="img"', html)
        self.assertIn("Focus neighborhood", html)
        self.assertIn("Open page", html)
        self.assertIn("&lt;fast &amp; &quot;bounded&quot;&gt;", html)
        self.assertIn("<script>var resetButton = true;</script>", html)

    def test_render_graph_page_body_omits_load_button_for_full_graph(self):
        html = render_graph_page_body(
            graph_js="<script></script>",
            node_count=3,
            edge_count=2,
            total_node_count=3,
            total_edge_count=2,
            graph_mode="full",
            graph_note="",
            category_options="",
            legend_items="",
        )

        self.assertNotIn("Load graph data", html)


if __name__ == "__main__":
    unittest.main()
