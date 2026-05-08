"""Shared web graph rendering helpers."""
from __future__ import annotations

import html
from typing import Any, Mapping


GRAPH_INITIAL_FULL_NODE_LIMIT = 900
GRAPH_INITIAL_SUMMARY_NODE_LIMIT = 250
GRAPH_INITIAL_SUMMARY_EDGE_LIMIT = 1000

GRAPH_CATEGORY_COLORS = {
    "concepts": "#4e79a7",
    "entities": "#f28e2b",
    "memories": "#edc948",
    "sources": "#59a14f",
    "comparisons": "#e15759",
    "explorations": "#76b7b2",
    "root": "#bab0ac",
}


def _visible_graph_parts(graph: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = [
        dict(node)
        for node in graph.get("nodes", [])
        if str(node.get("category") or "") != "root"
    ]
    ids = {str(node.get("id") or "") for node in nodes}
    edges = [
        {"source": str(edge.get("source") or ""), "target": str(edge.get("target") or "")}
        for edge in graph.get("edges", [])
        if str(edge.get("source") or "") in ids and str(edge.get("target") or "") in ids
    ]
    return nodes, edges


def graph_needs_bounded_overview(
    full_graph: Mapping[str, Any],
    full_node_limit: int = GRAPH_INITIAL_FULL_NODE_LIMIT,
) -> bool:
    """Return whether the graph page should start with a bounded overview."""
    nodes, _ = _visible_graph_parts(full_graph)
    return len(nodes) > full_node_limit


def graph_initial_payload(
    full_graph: Mapping[str, Any],
    summary_graph: Mapping[str, Any] | None = None,
    full_node_limit: int = GRAPH_INITIAL_FULL_NODE_LIMIT,
) -> dict[str, Any]:
    """Build the initial browser graph payload and total counts.

    The full graph remains available through the HTTP API. This helper decides
    whether the page should embed the full graph immediately or a bounded
    high-signal overview first.
    """
    full_nodes, full_edges = _visible_graph_parts(full_graph)
    total_node_count = len(full_nodes)
    total_edge_count = len(full_edges)
    graph_mode = "full"
    graph_note = ""
    visible_nodes = full_nodes
    visible_edges = full_edges

    if total_node_count > full_node_limit and summary_graph is not None:
        visible_nodes, visible_edges = _visible_graph_parts(summary_graph)
        graph_mode = "summary"
        graph_note = (
            f" Showing a fast overview of {len(visible_nodes)} high-signal nodes first; "
            f"load graph data when you need to search or filter across every page."
        )

    return {
        "nodes": visible_nodes,
        "edges": visible_edges,
        "node_count": len(visible_nodes),
        "edge_count": len(visible_edges),
        "total_node_count": total_node_count,
        "total_edge_count": total_edge_count,
        "graph_mode": graph_mode,
        "graph_note": graph_note,
    }


def graph_category_options(nodes: list[Mapping[str, Any]]) -> str:
    categories = sorted({
        str(node.get("category") or "")
        for node in nodes
        if str(node.get("category") or "") and str(node.get("category") or "") != "root"
    })
    return '<option value="all">all types</option>' + "".join(
        f'<option value="{html.escape(category, quote=True)}">{html.escape(category)}</option>'
        for category in categories
    )


def graph_legend_items(colors: Mapping[str, str] = GRAPH_CATEGORY_COLORS) -> str:
    return "".join(
        f'<span style="background:{html.escape(str(color), quote=True)}"></span>{html.escape(str(category))} '
        for category, color in colors.items()
        if category != "root"
    )
