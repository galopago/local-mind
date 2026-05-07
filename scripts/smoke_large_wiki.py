#!/usr/bin/env python3
"""Exercise Link's query and graph path against a synthetic large wiki."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.memory import memory_records  # noqa: E402
from link_core.query import query_link  # noqa: E402
from link_core.wiki import build_backlinks, build_wiki_cache, graph_data, search_pages  # noqa: E402


class SmokeFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def write_page(wiki: Path, rel: str, text: str) -> None:
    path = wiki / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_large_wiki(root: Path, page_count: int) -> Path:
    wiki = root / "wiki"
    wiki.mkdir(parents=True, exist_ok=True)
    write_page(wiki, "index.md", "# Index\n")
    write_page(wiki, "log.md", "# Log\n")

    source_count = max(12, min(40, page_count // 20))
    for index in range(source_count):
        write_page(
            wiki,
            f"sources/source-{index}.md",
            "---\n"
            "type: source\n"
            f"title: Source {index}\n"
            "---\n\n"
            f"# Source {index}\n\n"
            f"> **TLDR:** Source {index} covers local agent memory topic {index}.\n\n"
            "## Summary\n\nSynthetic source for large-wiki smoke coverage.\n\n"
            f"## Raw Source\n\n`raw/source-{index}.md`\n",
        )

    for index in range(page_count):
        next_index = (index + 1) % page_count
        skip_index = (index + 17) % page_count
        source_index = index % source_count
        write_page(
            wiki,
            f"concepts/topic-{index}.md",
            "---\n"
            "type: concept\n"
            f"title: Topic {index} Agent Memory\n"
            "tags: [agent-memory, large-wiki]\n"
            "---\n\n"
            f"# Topic {index} Agent Memory\n\n"
            f"> **TLDR:** Topic {index} describes local agent memory behavior.\n\n"
            "## Overview\n\n"
            f"Topic {index} links to [[topic-{next_index}]], [[topic-{skip_index}]], "
            f"and [[source-{source_index}]]. The repeated phrase keeps search realistic "
            "without requiring an unbounded context packet.\n\n"
            "## Sources\n\n"
            f"- [[source-{source_index}]]\n",
        )

    memory_count = max(16, min(40, page_count // 25))
    for index in range(memory_count):
        topic = 42 if index == 0 else index
        write_page(
            wiki,
            f"memories/prefer-topic-{topic}.md",
            "---\n"
            "type: memory\n"
            f"title: Prefer topic {topic}\n"
            "memory_type: preference\n"
            "scope: project\n"
            "project: large-wiki\n"
            "status: active\n"
            "date_captured: \"2026-05-06T00:00:00Z\"\n"
            "source: large-wiki-smoke\n"
            "review_status: reviewed\n"
            "---\n\n"
            f"# Prefer topic {topic}\n\n"
            f"> **TLDR:** User prefers topic {topic} local agent memory notes.\n\n"
            f"## Memory\n\nUser prefers topic {topic} local agent memory notes.\n",
        )

    (wiki / "_backlinks.json").write_text(json.dumps(build_backlinks(wiki)), encoding="utf-8")
    return wiki


def timed(label: str, fn):
    start = time.perf_counter()
    value = fn()
    elapsed = time.perf_counter() - start
    return label, value, elapsed


def run_smoke(work_dir: Path, page_count: int) -> dict[str, object]:
    wiki = build_large_wiki(work_dir, page_count)
    timings: dict[str, float] = {}

    label, cache, elapsed = timed("cache", lambda: build_wiki_cache(wiki))
    timings[label] = elapsed
    label, results, elapsed = timed("search", lambda: search_pages("agent memory", cache, limit=20))
    timings[label] = elapsed
    label, packet, elapsed = timed(
        "query",
        lambda: query_link(
            wiki,
            "agent memory",
            cache,
            memory_records(wiki),
            budget="small",
            project="large-wiki",
        ),
    )
    timings[label] = elapsed
    label, graph, elapsed = timed("graph", lambda: graph_data(cache))
    timings[label] = elapsed

    expected_pages = page_count + max(12, min(40, page_count // 20)) + max(16, min(40, page_count // 25)) + 2
    require(len(cache["pages"]) == expected_pages, f"expected {expected_pages} cached pages, got {len(cache['pages'])}")
    require(len(results) == 20, f"expected capped search results, got {len(results)}")
    require(packet.get("found") is True, "query_link did not find large-wiki context")
    require(len(packet.get("context_packet", [])) <= 6, "small query budget was not enforced")
    require(packet.get("budget_report", {}).get("wiki_search", {}).get("has_more") is True, "query did not report additional matches")
    require(packet.get("follow_up", [{}])[0].get("tool") == "query_link", "query did not return follow-up guidance")
    require(len(graph["nodes"]) == expected_pages, f"expected {expected_pages} graph nodes, got {len(graph['nodes'])}")
    require(len(graph["edges"]) >= page_count * 2, "graph edge count is unexpectedly low")

    return {
        "wiki": str(wiki),
        "pages": len(cache["pages"]),
        "edges": len(graph["edges"]),
        "context_items": len(packet.get("context_packet", [])),
        "search_results": len(results),
        "timings": {key: round(value, 4) for key, value in timings.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test Link against a synthetic large wiki.")
    parser.add_argument("--pages", type=int, default=1000, help="number of synthetic concept pages")
    parser.add_argument("--work-dir", default="", help="directory for generated wiki artifacts")
    args = parser.parse_args()

    if args.pages < 1:
        print("Large-wiki smoke failed: --pages must be at least 1", file=sys.stderr)
        return 2

    work_dir = Path(args.work_dir).expanduser().resolve() if args.work_dir else Path(tempfile.mkdtemp(prefix="link-large-wiki-"))
    try:
        payload = run_smoke(work_dir, args.pages)
    except SmokeFailure as exc:
        print(f"Large-wiki smoke failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2))
    print(f"Large-wiki smoke passed for {payload['pages']} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
