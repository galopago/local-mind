"""Shared benchmark health helpers for Link."""
from __future__ import annotations

from typing import Mapping


BENCHMARK_THRESHOLDS_SECONDS = {
    "cache": 5.0,
    "search": 1.0,
    "query": 3.0,
    "graph_summary": 1.0,
    "page_list": 0.5,
    "graph_initial": 1.0,
    "graph": 2.0,
}


def benchmark_health(payload: Mapping[str, object]) -> dict[str, object]:
    """Return a compact interactive-readiness verdict for benchmark output."""
    timings = payload.get("timings")
    if not isinstance(timings, Mapping):
        timings = {}
    warnings: list[str] = []
    slow_paths: list[str] = []
    for label, ceiling in BENCHMARK_THRESHOLDS_SECONDS.items():
        elapsed = timings.get(label)
        if isinstance(elapsed, (int, float)) and elapsed > ceiling:
            warnings.append(f"{label} took {elapsed:.4f}s, above the {ceiling:.1f}s interactive target")
            slow_paths.append(label)
    large_token_fallback = int(payload.get("pages") or 0) >= 1000 and payload.get("search_backend") != "sqlite-fts"
    if large_token_fallback:
        warnings.append("large wiki is using token-index fallback; SQLite FTS would improve search headroom")
    if warnings:
        summary = "Review recommended before relying on this wiki for interactive agent work."
        recommendations = [
            "Run link doctor --fix and link benchmark again after repairing wiki/index state.",
        ]
        if large_token_fallback or "search" in slow_paths or "query" in slow_paths:
            recommendations.append("Use a Python build with sqlite3/FTS5 enabled for large local wikis.")
        if "cache" in slow_paths:
            recommendations.append("Inspect unusually large pages or raw-source references; cache time is dominated by local file reads.")
        if "graph_initial" in slow_paths or "graph" in slow_paths:
            recommendations.append("Use graph-summary, search, and focused neighborhoods instead of loading the full graph first.")
        if "page_list" in slow_paths:
            recommendations.append("Use bounded page-list pagination instead of asking an agent to enumerate every page.")
        if not any(path in slow_paths for path in ("cache", "search", "query", "graph_summary", "page_list", "graph_initial", "graph")):
            recommendations.append("Inspect unusually large pages or raw-source references if interaction still feels slow.")
    else:
        summary = "Ready for interactive local agent memory."
        recommendations = []
    return {
        "status": "warn" if warnings else "pass",
        "label": "review" if warnings else "interactive",
        "summary": summary,
        "thresholds_seconds": BENCHMARK_THRESHOLDS_SECONDS,
        "warnings": warnings,
        "recommendations": recommendations,
    }


def render_benchmark_text(payload: Mapping[str, object]) -> str:
    """Render human-readable benchmark output."""
    lines = [
        f"Link benchmark: {payload.get('target', '')}",
        f"Query: {payload.get('query', '')}",
    ]
    project = payload.get("project")
    if project:
        lines.append(f"Project: {project}")
    lines.append("")
    lines.append(
        f"Scale: {payload.get('pages', 0)} pages · "
        f"{payload.get('memories', 0)} memories · "
        f"{payload.get('edges', 0)} edges"
    )
    lines.append(f"Search backend: {payload.get('search_backend', 'unknown')}")
    lines.append(
        f"Results: {payload.get('search_results', 0)} search results · "
        f"{payload.get('context_items', 0)} context items"
    )

    graph_summary = payload.get("graph_summary")
    page_list = payload.get("page_list")
    graph_initial = payload.get("graph_initial")
    if isinstance(graph_summary, Mapping) and isinstance(page_list, Mapping):
        lines.append(
            "Agent-safe payloads: "
            f"graph summary {graph_summary.get('returned_nodes', 0)} nodes/"
            f"{graph_summary.get('returned_edges', 0)} edges · "
            f"page list {page_list.get('returned_count', 0)} pages"
        )
    if isinstance(graph_initial, Mapping):
        lines.append(
            "Graph page initial load: "
            f"{graph_initial.get('mode', 'unknown')} · "
            f"{graph_initial.get('nodes', 0)}/{graph_initial.get('total_nodes', 0)} nodes"
        )

    health = payload.get("health")
    if isinstance(health, Mapping):
        lines.append(f"Verdict: {health.get('label', 'unknown')}")
        if health.get("summary"):
            lines.append(f"Health: {health.get('summary')}")

    lines.append("")
    lines.append("Timings")
    timings = payload.get("timings")
    if not isinstance(timings, Mapping):
        timings = {}
    for key in ("cache", "search", "query", "graph_summary", "page_list", "graph_initial", "graph"):
        value = timings.get(key, 0)
        if not isinstance(value, (int, float)):
            value = 0
        lines.append(f"- {key}: {value:.4f}s")

    if isinstance(health, Mapping) and health.get("warnings"):
        lines.append("")
        lines.append("Warnings")
        for warning in health["warnings"]:
            lines.append(f"- {warning}")
        recommendations = health.get("recommendations")
        if isinstance(recommendations, list) and recommendations:
            lines.append("")
            lines.append("Recommendations")
            for recommendation in recommendations:
                lines.append(f"- {recommendation}")

    budget_report = payload.get("budget_report")
    if isinstance(budget_report, Mapping):
        packet_report = budget_report.get("context_packet")
        if isinstance(packet_report, Mapping):
            lines.append("")
            lines.append(
                "Packet: "
                f"{packet_report.get('estimated_chars', 0)} chars · "
                f"{packet_report.get('estimated_tokens', 0)} tokens · "
                f"has_more={packet_report.get('has_more', False)}"
            )

    lines.append("")
    lines.append(f"Result: {'found' if payload.get('found') else 'no matching context'}")
    return "\n".join(lines)
