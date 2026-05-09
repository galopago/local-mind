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
