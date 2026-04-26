# link-mcp

<!-- mcp-name: io.github.gowtham0992/link -->

MCP server for the [Link](https://github.com/gowtham0992/link) personal knowledge wiki.

Exposes your wiki as MCP tools so any MCP-compatible agent can search, query context, and traverse the knowledge graph without reading files directly.

## Install

```bash
pip install link-mcp
```

## Setup

1. Install Link and scaffold your wiki:
```bash
git clone https://github.com/gowtham0992/link.git
bash link/integrations/kiro/install.sh
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

Or with a custom wiki path:
```json
{
  "mcpServers": {
    "link": {
      "command": "python3",
      "args": ["-m", "link_mcp", "--wiki", "/path/to/wiki"]
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `search_wiki` | Ranked search by title, alias, tag, fulltext |
| `get_context` | Topic + full graph neighborhood in one call |
| `get_pages` | List all pages with metadata |
| `get_backlinks` | Inbound + forward links for a page |
| `get_graph` | All nodes + edges |
| `rebuild_backlinks` | Rebuild the link index |

## Wiki location

By default uses `~/link/wiki/`. Override with `--wiki /path/to/wiki`.
