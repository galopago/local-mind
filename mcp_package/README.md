# link-mcp

<!-- mcp-name: io.github.gowtham0992/link -->

MCP server for [Link](https://github.com/gowtham0992/link), local personal memory for agents. Exposes memories and wiki context as MCP tools so agents can recall preferences, decisions, project context, sources, and graph neighborhoods without reading files directly.

Listed on the [official MCP Registry](https://registry.modelcontextprotocol.io) as `io.github.gowtham0992/link`.

Release notes: [CHANGELOG.md](https://github.com/gowtham0992/link/blob/main/CHANGELOG.md)

## Install

```bash
python3 -m pip install --upgrade link-mcp
```

If macOS/Homebrew Python reports `externally-managed-environment`, install into a dedicated venv:

```bash
python3 -m venv ~/.link-mcp-venv
~/.link-mcp-venv/bin/python -m pip install --upgrade pip link-mcp
```

Then use the venv Python in your MCP config:

```json
{
  "mcpServers": {
    "link": {
      "command": "/Users/YOU/.link-mcp-venv/bin/python",
      "args": ["-m", "link_mcp", "--wiki", "/Users/YOU/link/wiki"]
    }
  }
}
```

Replace `/Users/YOU` with your absolute home path.

## Quick setup (Kiro)

```bash
git clone https://github.com/gowtham0992/link.git
bash link/integrations/kiro/install.sh
```

This installs `link-mcp`, scaffolds `~/link/`, and registers the MCP server in `~/.kiro/settings/mcp.json` automatically.

## Manual setup (any MCP client)

1. Scaffold your wiki:
```bash
git clone https://github.com/gowtham0992/link.git
bash link/integrations/kiro/install.sh   # or claude-code, cursor, codex
```

2. Add to your MCP client config:
```json
{
  "mcpServers": {
    "link": {
      "command": "python3",
      "args": ["-m", "link_mcp"]
    }
  }
}
```

Custom wiki path:
```json
{
  "mcpServers": {
    "link": {
      "command": "python3",
      "args": ["-m", "link_mcp", "--wiki", "~/my-wiki/wiki"]
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `memory_brief(query?, limit?, project?)` | Prime the agent before answering or coding with profile counts, relevant memories, review warnings, and safe memory rules. |
| `memory_profile(limit?, project?)` | Summarize what Link remembers by type, scope, status, recency, preferences, decisions, and project context. |
| `memory_inbox(limit?, include_archived?)` | List memories that need user review, cleanup, or stronger metadata with primary actions and tool-call hints. |
| `review_memory(identifier, note?)` | Mark a confirmed memory as reviewed. |
| `explain_memory(identifier)` | Explain provenance, lifecycle, graph links, review issues, and recall readiness for one memory. |
| `recall_memory(query, limit?, include_archived?, project?)` | Search durable local memories for preferences, decisions, and project context. |
| `remember_memory(memory, title?, memory_type?, scope?, tags?, source?, allow_duplicate?, allow_conflict?, project?)` | Save an explicit user-approved local memory under `wiki/memories/`; strong duplicates and likely conflicts require explicit override. |
| `propose_memories(text, source?, limit?, project?)` | Propose durable memories from chat/session notes without writing them. |
| `capture_session(text, title?, source?, limit?, project?)` | Save long chat/session notes under `raw/memory-captures/` and return proposal-only memory candidates plus secret-looking content warnings. |
| `accept_capture(capture, index?, title?, memory_type?, scope?, tags?, project?, allow_duplicate?, allow_conflict?)` | Accept one proposal from a saved raw capture using duplicate/conflict-safe memory writes. |
| `redact_capture(capture, replacement?)` | Redact secret-looking values from a saved raw capture after user approval. |
| `delete_capture(capture, confirm?)` | Delete a saved raw capture after explicit confirmation. |
| `update_memory(identifier, memory, source?, allow_conflict?, project?)` | Merge new information into an existing memory, blocking likely conflicts with other active memories by default. |
| `archive_memory(identifier, reason?)` | Archive stale or wrong memory without deleting the Markdown page. |
| `restore_memory(identifier)` | Restore archived memory to active status. |
| `search_wiki(query, limit?)` | Ranked search — title (20pts), alias (8pts), tag (5pts), fulltext (2pts). Returns scores + snippets. |
| `get_context(topic)` | **Primary tool.** Best matching page (full content) + inbound/forward graph links in one call. |
| `get_pages(category?, type?, maturity?)` | All pages with metadata. Filter by category, type, or maturity. |
| `get_backlinks(page_name)` | Inbound + forward links for a page. |
| `get_graph()` | All nodes + edges for graph reasoning. |
| `rebuild_backlinks()` | Rebuild `_backlinks.json` after ingest or lint. |

Start with `memory_brief`, passing the user's task as `query` when available. Pass `project` for repo-specific work so Link returns broad user/global memory plus that project's memory, while keeping other explicit projects out of recall and duplicate/conflict checks. Use `memory_profile` to inspect the user/project memory shape, `memory_inbox` to find memories needing human review and the primary action for each item, `explain_memory` to audit why a memory exists, then `recall_memory` for focused preferences, decisions, and project context. Use `capture_session` for long chat/session notes that should be preserved locally before approval; use `propose_memories` when no raw capture is needed. Both return candidates only. If `capture_session` reports secret warnings, ask before calling `redact_capture`. Use `accept_capture` only after the user approves one captured proposal. Use `delete_capture` only after explicit user confirmation. If `remember_memory` or `accept_capture` returns duplicate candidates, use `update_memory` on the existing memory unless the user confirms a separate memory. If it returns conflict candidates, ask the user whether to update or archive the older memory before forcing a conflict. Use `archive_memory`, not deletion, when a memory is stale or wrong. Use `get_context` for source-backed topic answers — one call returns the primary page plus all related pages via graph traversal.

## Wiki location

Default: `~/link/wiki/`. Override with `--wiki /path/to/wiki`.

## Requirements

- Python 3.10+
- A Link wiki (scaffolded by `install.sh`)
