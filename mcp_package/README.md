# link-mcp

<!-- mcp-name: io.github.gowtham0992/link -->

MCP server for the [Link](https://github.com/gowtham0992/link) personal knowledge wiki. Exposes your wiki as MCP tools — search, query context, and traverse the knowledge graph without reading files directly.

Listed on the [official MCP Registry](https://registry.modelcontextprotocol.io) as `io.github.gowtham0992/link`.

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
| `search_wiki(query, limit?)` | Ranked search — title (20pts), alias (8pts), tag (5pts), fulltext (2pts). Returns scores + snippets. |
| `get_context(topic)` | **Primary tool.** Best matching page (full content) + inbound/forward graph links in one call. |
| `get_pages(category?, type?, maturity?)` | All pages with metadata. Filter by category, type, or maturity. |
| `get_backlinks(page_name)` | Inbound + forward links for a page. |
| `get_graph()` | All nodes + edges for graph reasoning. |
| `rebuild_backlinks()` | Rebuild `_backlinks.json` after ingest or lint. |

**Use `get_context` for answering questions** — one call returns the primary page plus all related pages via graph traversal. Eliminates the token waste of reading index.md every session.

## Wiki location

Default: `~/link/wiki/`. Override with `--wiki /path/to/wiki`.

## Requirements

- Python 3.10+
- A Link wiki (scaffolded by `install.sh`)
