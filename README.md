<p align="center">
  <img src="logo.svg" alt="Link" width="120">
</p>

# Link

A personal knowledge wiki maintained by LLMs. Knowledge compounds — every source you add makes the wiki richer, every question you ask gets filed back.

Implements the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) with a production-ready local server, agent-optimized search API, and interactive graph visualization.

[![GitHub](https://img.shields.io/github/stars/gowtham0992/link?style=flat)](https://github.com/gowtham0992/link)
[![MCP Registry](https://img.shields.io/badge/MCP_Registry-io.github.gowtham0992%2Flink-blue)](https://registry.modelcontextprotocol.io/?q=io.github.gowtham0992%2Flink)
[![PyPI](https://img.shields.io/pypi/v/link-mcp)](https://pypi.org/project/link-mcp/)

## How it works

1. Drop sources (articles, papers, notes, images) into `raw/`
2. Tell your LLM agent: "ingest this" — it reads the source and compiles structured wiki pages
3. The wiki grows over time. Ask questions, get answers filed back. Knowledge compounds.

You never write the wiki yourself. The LLM writes and maintains all of it. You curate sources and ask questions.

## Setup

```bash
git clone https://github.com/gowtham0992/link.git
bash link/integrations/kiro/install.sh          # Kiro
bash link/integrations/claude-code/install.sh   # Claude Code
bash link/integrations/antigravity/install.sh   # Google Antigravity
bash link/integrations/codex/install.sh         # Codex
bash link/integrations/cursor/install.sh        # Cursor
bash link/integrations/copilot/install.sh       # Copilot
bash link/integrations/vscode/install.sh        # VS Code
```

This does two things: (1) makes your agent aware of Link in every session, and (2) scaffolds a central wiki at `~/link/`.

For project-specific wikis, add `--project`. See [integrations/](integrations/) for details.

**Updating after a git pull:** run `install.sh` again — it detects existing wikis and only updates code files (`serve.py`, `LINK.md`, integrations), never your wiki data (`wiki/index.md`, `wiki/log.md`, your pages). Safe to run anytime.

## Viewing the wiki

**Obsidian:** open the `wiki/` folder as a vault. Wikilinks, graph view, and tags all work natively.

**Web browser:**
```bash
python serve.py
# → http://localhost:3000
```

Wikipedia-style local viewer. No dependencies beyond Python 3.10+. Features:
- Full-text search with result highlighting (`/` to focus)
- Interactive knowledge graph at `/graph` — force-directed, click to navigate
- Dark mode, keyboard navigation (`j`/`k` to move, `Escape` to blur)

## MCP Server

Link is listed on the [official MCP Registry](https://registry.modelcontextprotocol.io/?q=io.github.gowtham0992%2Flink) as `io.github.gowtham0992/link`.

```bash
pip install link-mcp
```

Point it at your wiki and add to your MCP client config:

```json
{
  "mcpServers": {
    "link": {
      "command": "python3",
      "args": ["-m", "link_mcp", "--wiki", "~/link/wiki"]
    }
  }
}
```

That's it. No cloning required if you already have a wiki.

> **Don't have a wiki yet?** Run `bash link/integrations/kiro/install.sh` after cloning — it scaffolds `~/link/`, installs `link-mcp`, and registers it in your MCP config automatically.

**Available tools:**

| Tool | Description |
|------|-------------|
| `search_wiki` | Ranked search by title, alias, tag, fulltext. Returns scores + snippets. |
| `get_context` | **Primary tool.** Topic + full graph neighborhood in one call. |
| `get_pages` | List all pages with metadata. Filter by category, type, maturity. |
| `get_backlinks` | Inbound + forward links for a page. |
| `get_graph` | All nodes + edges for graph reasoning. |
| `rebuild_backlinks` | Rebuild `_backlinks.json` after ingest or lint. |

## API (HTTP)

`serve.py` also exposes a local HTTP API. Same capabilities as the MCP tools, accessible over HTTP when the server is running.

> **⚠️ Local use only.** `serve.py` binds to `127.0.0.1` and has no authentication. Do not expose it to the internet without adding auth.

| Endpoint | Description |
|----------|-------------|
| `GET /api/pages` | All pages with title, type, tags, aliases, maturity, tldr |
| `GET /api/search?q=<query>` | Ranked search — title (20pts), alias (8pts), tag (5pts), fulltext (2pts) |
| `GET /api/context?topic=<topic>` | **Primary endpoint.** Best matching page + inbound/forward graph links |
| `GET /api/graph` | All nodes + edges for graph visualization |
| `GET /api/backlinks` | Reverse + forward link index |
| `GET /api/rebuild-backlinks` | Rebuild `_backlinks.json` by scanning all wikilinks |

Search is O(1) via in-memory inverted token index — sub-millisecond at any wiki size. Use `/api/context?topic=X` over reading files manually — one call returns the primary page + all related pages via graph traversal.

## Structure

```
link/
├── LINK.md              ← schema (instructions for the LLM)
├── raw/                 ← your source documents (immutable)
├── wiki/                ← compiled knowledge (LLM-maintained)
│   ├── index.md         ← master catalog
│   ├── _backlinks.json  ← reverse + forward link index (auto-generated)
│   ├── log.md           ← append-only operation history
│   ├── sources/         ← one page per ingested source
│   ├── concepts/        ← topic articles
│   ├── entities/        ← people, orgs, projects
│   ├── comparisons/     ← side-by-side analyses
│   └── explorations/    ← filed query results
├── integrations/        ← one-step setup per AI tool
├── serve.py             ← local web viewer + API server
└── .linkignore          ← files to skip
```

## Operations

| Command | What it does |
|---------|-------------|
| "ingest this" | Process a source from raw/ into wiki pages |
| "what is X?" | Query the wiki, optionally file the answer back |
| "lint the wiki" | Health check: orphans, dead links, stale claims, confidence gaps |
| "research X" | Find sources on the web, capture a chat, or analyze wiki gaps |

## Design principles

- **Every claim links to its source.** No orphan claims. Confidence tags on every fact: `[confidence: high/medium/low]`.
- **Audit trail built-in.** `log.md` is append-only — every ingest, query, and lint is recorded. `_backlinks.json` tracks the full graph.
- **Pages mature over time.** seed → growing → mature → established. The wiki gets richer, not just bigger.
- **Agent-optimized.** `/api/context` returns a page + its graph neighborhood in one call. Agents don't re-derive context from scratch every session.
- **No external dependencies.** Pure Python stdlib. No vector databases, no embedding APIs, no npm.
- **The wiki is just markdown files in a git repo.** Version history, branching, and collaboration for free.
