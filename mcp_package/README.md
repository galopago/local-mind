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
| `link_status(include_validation?)` | Readiness summary with package version, wiki path, page/memory counts, optional validation summary, and safe next actions. |
| `migrate_wiki()` | Apply safe, idempotent wiki schema migrations when `link_status` reports a missing or old schema marker. |
| `ingest_status()` | Raw source ingest state with pending files, graph health, the next agent prompt, guided plan, and follow-up checks. |
| `query_link(query, budget?, project?)` | Build a compact answer-ready packet from local memory, ranked wiki search, graph-neighborhood context, budget reports, and follow-up actions. |
| `validate_wiki(strict?)` | Validate agent-generated wiki pages after ingest or large edits: frontmatter, type/directory alignment, required sections, dead links, and backlink freshness. |
| `backup_wiki(label?, include_raw?, list_only?)` | Create or list local `.link-backups/` archives before broad repairs or risky wiki edits; raw sources are excluded by default. |
| `memory_brief(query?, limit?, project?)` | Prime the agent before answering or coding with profile counts, relevant memories, review warnings, and safe memory rules. |
| `memory_audit(limit?, project?)` | Read-only health report for memory review backlog, saved raw captures, risk factors, and next actions. |
| `memory_profile(limit?, project?)` | Summarize what Link remembers by type, scope, status, recency, preferences, decisions, and project context. |
| `memory_inbox(limit?, include_archived?)` | List memories that need user review, cleanup, or stronger metadata with primary actions and tool-call hints. |
| `review_memory(identifier, note?)` | Mark a confirmed memory as reviewed. |
| `explain_memory(identifier)` | Explain provenance, lifecycle, graph links, review issues, and recall readiness for one memory. |
| `recall_memory(query, limit?, include_archived?, project?)` | Search durable local memories for preferences, decisions, and project context. |
| `remember_memory(memory, title?, memory_type?, scope?, tags?, source?, allow_duplicate?, allow_conflict?, project?)` | Save an explicit user-approved local memory under `wiki/memories/`; strong duplicates and likely conflicts require explicit override. |
| `propose_memories(text, source?, limit?, project?)` | Propose durable memories from chat/session notes without writing them. |
| `capture_session(text, title?, source?, limit?, project?)` | Save long chat/session notes under `raw/memory-captures/` and return proposal-only memory candidates plus secret-looking content warnings. |
| `capture_inbox(limit?, project?)` | Review saved raw captures with redacted snippets, secret-warning labels, and accept/redact/delete commands. |
| `accept_capture(capture, index?, title?, memory_type?, scope?, tags?, project?, allow_duplicate?, allow_conflict?)` | Accept one proposal from a saved raw capture using duplicate/conflict-safe memory writes. |
| `redact_capture(capture, replacement?)` | Redact secret-looking values from a saved raw capture after user approval. |
| `delete_capture(capture, confirm?)` | Delete a saved raw capture after explicit confirmation. |
| `update_memory(identifier, memory, source?, allow_conflict?, project?)` | Merge new information into an existing memory, blocking likely conflicts with other active memories by default. |
| `archive_memory(identifier, reason?)` | Archive stale or wrong memory without deleting the Markdown page. |
| `restore_memory(identifier)` | Restore archived memory to active status. |
| `forget_memory(identifier, confirm?)` | Permanently delete a memory only after explicit user confirmation; prefer archive for reversible cleanup. |
| `search_wiki(query, limit?)` | Ranked search — title (20pts), alias (8pts), tag (5pts), fulltext (2pts). Returns scores + snippets. |
| `get_context(topic)` | **Primary tool.** Best matching page (full content) + inbound/forward graph links in one call. |
| `get_pages(category?, type?, maturity?)` | All pages with metadata. Filter by category, type, or maturity. |
| `get_backlinks(page_name)` | Inbound + forward links for a page. |
| `get_graph()` | All nodes + edges for graph reasoning. |
| `rebuild_index()` | Regenerate `wiki/index.md` from current pages so the human-readable catalog stays complete. |
| `rebuild_backlinks()` | Rebuild `_backlinks.json` after ingest or lint. |

Use `link_status` when connecting to Link or troubleshooting setup; if it reports a missing or old schema marker, call `migrate_wiki` before other writes. Use `ingest_status` when the user drops files into `raw/` or asks what still needs ingest. Start with `query_link` for substantive questions that may need both local memory and wiki context. If `budget_report` says context was truncated, use the returned `follow_up` action before scanning files manually. Use `memory_brief`, passing the user's task as `query` when available, at session start or before personalized/project work. Pass `project` for repo-specific work so Link returns broad user/global memory plus that project's memory, while keeping other explicit projects out of recall and duplicate/conflict checks. After ingesting sources or substantially editing wiki pages, call `rebuild_index`, `rebuild_backlinks`, then `validate_wiki`, before saying the wiki is updated. Use `backup_wiki` before broad repairs or risky local wiki edits; raw sources are excluded unless the user explicitly asks to include them. Use `memory_profile` to inspect the user/project memory shape, `memory_audit` to see review/capture risks, `memory_inbox` to find memories needing human review and the primary action for each item, `explain_memory` to audit why a memory exists, then `recall_memory` for focused preferences, decisions, and project context. Use `capture_session` for long chat/session notes that should be preserved locally before approval; use `propose_memories` when no raw capture is needed. Both return candidates only. Use `capture_inbox` to review saved captures before accepting, redacting, or deleting them. If `capture_session` reports secret warnings, ask before calling `redact_capture`. Use `accept_capture` only after the user approves one captured proposal. Use `delete_capture` only after explicit user confirmation. If `remember_memory` or `accept_capture` returns duplicate candidates, use `update_memory` on the existing memory unless the user confirms a separate memory. If it returns conflict candidates, ask the user whether to update or archive the older memory before forcing a conflict. Use `archive_memory`, not deletion, when a memory is stale or wrong. Use `forget_memory` only when the user explicitly asks for permanent deletion. Use `get_context` when you need the full primary source page after `query_link` shows it is relevant.

## Wiki location

Default: `~/link/wiki/`. Override with `--wiki /path/to/wiki`.

## Requirements

- Python 3.10+
- A Link wiki (scaffolded by `install.sh`)
