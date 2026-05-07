"""Shared benchmark health helpers for Link."""
from __future__ import annotations

from typing import Mapping


BENCHMARK_THRESHOLDS_SECONDS = {
    "cache": 5.0,
    "search": 1.0,
    "query": 3.0,
    "graph": 2.0,
}


def benchmark_health(payload: Mapping[str, object]) -> dict[str, object]:
    """Return a compact interactive-readiness verdict for benchmark output."""
    timings = payload.get("timings")
    if not isinstance(timings, Mapping):
        timings = {}
    warnings: list[str] = []
    for label, ceiling in BENCHMARK_THRESHOLDS_SECONDS.items():
        elapsed = timings.get(label)
        if isinstance(elapsed, (int, float)) and elapsed > ceiling:
            warnings.append(f"{label} took {elapsed:.4f}s, above the {ceiling:.1f}s interactive target")
    if int(payload.get("pages") or 0) >= 1000 and payload.get("search_backend") != "sqlite-fts":
        warnings.append("large wiki is using token-index fallback; SQLite FTS would improve search headroom")
    if warnings:
        summary = "Review recommended before relying on this wiki for interactive agent work."
        recommendations = [
            "Use SQLite FTS for large wikis when available.",
            "Run link doctor --fix and link benchmark again after repairing wiki/index state.",
            "If one timing path stays slow, inspect unusually large pages or raw-source references.",
        ]
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
