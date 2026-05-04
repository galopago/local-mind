<p align="center">
  <img src="logo.svg" alt="Link" width="120">
</p>

# Link

A personal knowledge wiki maintained by LLMs. Knowledge compounds — every source you add makes the wiki richer, every question you ask gets filed back.

Implements the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) with a production-ready local server, agent-optimized search API, and interactive graph visualization.

[![GitHub](https://img.shields.io/github/stars/gowtham0992/link?style=flat)](https://github.com/gowtham0992/link)
[![CI](https://github.com/gowtham0992/link/actions/workflows/ci.yml/badge.svg)](https://github.com/gowtham0992/link/actions/workflows/ci.yml)
[![MCP Registry](https://img.shields.io/badge/MCP_Registry-io.github.gowtham0992%2Flink-blue)](https://registry.modelcontextprotocol.io/?q=io.github.gowtham0992%2Flink)
[![PyPI](https://img.shields.io/pypi/v/link-mcp)](https://pypi.org/project/link-mcp/)

## How it works

1. Drop sources (articles, papers, notes, images) into `raw/`
2. Tell your LLM agent: "ingest this" — it reads the source and compiles structured wiki pages
3. The wiki grows over time. Ask questions, get answers filed back. Knowledge compounds.

You never write the wiki yourself. The LLM writes and maintains all of it. You curate sources and ask questions.

## Try the demo

Create a pre-ingested sample wiki before touching your own data:

```bash
git clone https://github.com/gowtham0992/link.git
cd link
python3 link.py demo
cd link-demo
python3 serve.py
```

Then open:

- `http://localhost:3000`
- `http://localhost:3000/graph`

The demo shows raw notes, compiled pages, backlinks, MCP-friendly context, and the graph view working together.

Check the demo wiki:

```bash
python3 link.py ingest-status .
python3 link.py doctor .
```

`doctor` verifies the wiki structure, dead links, stale backlinks, index drift, page summaries, source sections, `source_count` metadata, isolated graph nodes, raw-source coverage, and secret-looking filenames or file contents.

## First 10 minutes

Use this path when you want to try Link, then turn one real note into local agent memory.

### 1. See the finished shape

```bash
git clone https://github.com/gowtham0992/link.git
cd link
python3 link.py demo
cd link-demo
python3 serve.py
```

Open `http://localhost:3000/graph`. The demo shows what a healthy Link memory looks like: raw notes, source pages, concept pages, backlinks, graph context, and MCP-ready retrieval.

### 2. Create your own wiki

In a separate terminal:

```bash
cd link
bash integrations/kiro/install.sh
```

Use the installer for your agent if it is not Kiro:

- `integrations/codex/install.sh`
- `integrations/claude-code/install.sh`
- `integrations/cursor/install.sh`
- `integrations/copilot/install.sh`
- `integrations/vscode/install.sh`
- `integrations/antigravity/install.sh`

This creates `~/link/`, installs `link-mcp`, and writes lightweight agent instructions.

### 3. Add one real source

```bash
cat > ~/link/raw/first-memory.md <<'EOF'
---
title: "First Link memory"
source_type: note
date_captured: 2026-05-03
---

# First Link memory

I am testing Link as local personal memory for agents.
The important idea is that raw notes stay local, and the agent turns them into source-cited wiki pages.
EOF
```

Check what is pending:

```bash
python3 ~/link/link.py ingest-status ~/link
```

### 4. Ask your agent to ingest it

In your agent chat, say:

```text
ingest raw/first-memory.md into Link
```

The agent should read `~/link/LINK.md`, create a source page under `wiki/sources/`, create or update related concept/entity pages, update `wiki/index.md`, append `wiki/log.md`, and rebuild backlinks.

### 5. Verify the memory

```bash
python3 ~/link/link.py doctor ~/link --fix
python3 ~/link/link.py ingest-status ~/link
python3 ~/link/link.py verify-mcp ~/link
```

Then ask your MCP-enabled agent:

```text
query Link for first Link memory
```

If the agent can answer from Link, the local memory loop is working.

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
python3 -m pip install --upgrade link-mcp
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

Verify MCP setup from a Link checkout:

```bash
python3 link.py verify-mcp .
```

> **Don't have a wiki yet?** Run `bash link/integrations/kiro/install.sh` after cloning — it scaffolds `~/link/`, installs `link-mcp`, and registers it in your MCP config automatically.

**macOS/Homebrew Python:** if pip reports `externally-managed-environment`, use a dedicated venv and point your MCP client at that Python:

```bash
python3 -m venv ~/.link-mcp-venv
~/.link-mcp-venv/bin/python -m pip install --upgrade pip link-mcp
```

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

Replace `/Users/YOU` with your absolute home path. The one-step Link installers handle this automatically for most users.

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

## Privacy and release safety

Link is local-first:
- No telemetry.
- No hosted backend.
- No external API calls from `serve.py` or `link-mcp`.
- Raw sources and generated wiki pages are ignored by git by default.
- Registry token files (`.mcpregistry_*`, `*.token`) are ignored and excluded from PyPI source distributions.

If you publish or share Link, use `git push`, `git archive`, or a clean release artifact. Do not zip an entire working directory, because local-only files such as `.git/`, ignored raw sources, ignored wiki pages, build outputs, and editor caches can be included by accident.

Before sharing a wiki or demo, run:

```bash
python3 link.py doctor .
```

Treat errors as release blockers. Warnings are usually quality work: missing summaries, missing source sections, stale source counts, or isolated pages.

If the only error is stale backlinks, repair the graph index locally:

```bash
python3 link.py rebuild-backlinks .
```

## Release flow

Use branches and CI for public releases:

1. Create a branch such as `codex/ci-trust-gates`.
2. Make the release changes and bump the MCP package version in `mcp_package/pyproject.toml`, `mcp_package/server.json`, and `mcp_package/link_mcp/__init__.py`.
3. Open a PR into `main`.
4. Merge only after CI passes.
5. Tag the exact merged release commit on `main`.
6. Publish `link-mcp` to PyPI, then publish the MCP registry entry.

For a patch release:

```bash
git switch main
git pull --ff-only
git tag -a v1.0.5 -m "v1.0.5"
git push origin v1.0.5
cd mcp_package
rm -rf dist ./*.egg-info
python3 -m build
python3 -m twine check dist/*
TWINE_USERNAME=__token__ python3 -m twine upload dist/*
mcp-publisher publish
```

Never reuse a published PyPI version or move a public release tag. If a release needs another fix, bump to the next version.

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

Local utility commands:

```bash
python3 link.py demo              # create ./link-demo with a pre-ingested sample wiki
python3 link.py ingest-status link-demo  # show raw files still pending ingestion
python3 link.py doctor link-demo  # check structure, graph health, source hygiene, and secret-looking content
python3 link.py doctor link-demo --fix  # safely create missing structure and repair backlinks
python3 link.py rebuild-backlinks link-demo  # regenerate wiki/_backlinks.json without starting the server
python3 link.py verify-mcp link-demo  # verify link-mcp import and print MCP client config
```

## Design principles

- **Every claim links to its source.** No orphan claims. Confidence tags on every fact: `[confidence: high/medium/low]`.
- **Audit trail built-in.** `log.md` is append-only — every ingest, query, and lint is recorded. `_backlinks.json` tracks the full graph.
- **Pages mature over time.** seed → growing → mature → established. The wiki gets richer, not just bigger.
- **Agent-optimized.** `/api/context` returns a page + its graph neighborhood in one call. Agents don't re-derive context from scratch every session.
- **No external dependencies.** Pure Python stdlib. No vector databases, no embedding APIs, no npm.
- **The wiki is just markdown files in a git repo.** Version history, branching, and collaboration for free.
