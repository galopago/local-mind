#!/usr/bin/env python3
"""Smoke test a real Link MCP stdio server with the MCP client SDK."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any


EXPECTED_TOOLS = {
    "query_link",
    "search_wiki",
    "get_context",
    "get_graph",
    "recall_memory",
    "memory_profile",
    "explain_memory",
}


def _json_text(result: Any, tool_name: str) -> dict[str, Any]:
    is_error = getattr(result, "isError", getattr(result, "is_error", False))
    if is_error:
        raise RuntimeError(f"{tool_name} returned an MCP error result")
    if not result.content:
        raise RuntimeError(f"{tool_name} returned no content")
    text = getattr(result.content[0], "text", "")
    if not text:
        raise RuntimeError(f"{tool_name} returned non-text content")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{tool_name} returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{tool_name} returned JSON {type(payload).__name__}, expected object")
    return payload


async def _run_smoke(wiki_dir: Path, python: str) -> None:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    server = StdioServerParameters(
        command=python,
        args=["-m", "link_mcp", "--wiki", str(wiki_dir)],
        env=os.environ.copy(),
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            listed = await session.list_tools()
            tool_names = {tool.name for tool in listed.tools}
            missing = sorted(EXPECTED_TOOLS - tool_names)
            if missing:
                raise RuntimeError(f"missing MCP tools: {', '.join(missing)}")

            search = _json_text(
                await session.call_tool(
                    "search_wiki",
                    {"query": "agent memory", "limit": 3},
                    read_timeout_seconds=timedelta(seconds=10),
                ),
                "search_wiki",
            )
            if search.get("count", 0) < 1 or search["results"][0]["name"] != "agent-memory":
                raise RuntimeError("search_wiki did not return the expected demo result")

            context = _json_text(
                await session.call_tool(
                    "get_context",
                    {"topic": "agent memory"},
                    read_timeout_seconds=timedelta(seconds=10),
                ),
                "get_context",
            )
            if not context.get("found") or context.get("primary") != "agent-memory":
                raise RuntimeError("get_context did not return the expected primary page")

            profile = _json_text(
                await session.call_tool(
                    "memory_profile",
                    {},
                    read_timeout_seconds=timedelta(seconds=10),
                ),
                "memory_profile",
            )
            if profile.get("memory_count", 0) < 1:
                raise RuntimeError("memory_profile did not see the demo memory")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test Link MCP over stdio.")
    parser.add_argument("wiki", help="path to a Link wiki directory")
    parser.add_argument("--python", default=sys.executable, help="Python executable used to run -m link_mcp")
    args = parser.parse_args()

    wiki_dir = Path(args.wiki).expanduser().resolve()
    if not (wiki_dir / "index.md").exists():
        print(f"MCP smoke failed: {wiki_dir} does not look like a Link wiki", file=sys.stderr)
        return 1

    try:
        import anyio

        anyio.run(_run_smoke, wiki_dir, args.python)
    except Exception as exc:
        print(f"MCP smoke failed: {exc}", file=sys.stderr)
        return 1

    print(f"MCP stdio smoke passed for {wiki_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
