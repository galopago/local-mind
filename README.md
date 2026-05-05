<p align="center">
  <img src="logo.svg" alt="Link" width="120">
</p>

# Link

Local personal memory for LLM agents.

Link turns raw sources into a local Markdown wiki that agents can search, cite, traverse, and maintain over time. It implements the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): keep knowledge outside the chat window, make every claim inspectable, and let the memory compound.

[![GitHub](https://img.shields.io/github/stars/gowtham0992/link?style=flat)](https://github.com/gowtham0992/link)
[![CI](https://github.com/gowtham0992/link/actions/workflows/ci.yml/badge.svg)](https://github.com/gowtham0992/link/actions/workflows/ci.yml)
[![MCP Registry](https://img.shields.io/badge/MCP_Registry-io.github.gowtham0992%2Flink-blue)](https://registry.modelcontextprotocol.io/?q=io.github.gowtham0992%2Flink)
[![PyPI](https://img.shields.io/pypi/v/link-mcp)](https://pypi.org/project/link-mcp/)

Release notes: [CHANGELOG.md](CHANGELOG.md)

## Quick Start

Try a finished, pre-ingested wiki before touching your own files:

```bash
git clone https://github.com/gowtham0992/link.git
cd link
python3 link.py demo
cd link-demo
python3 serve.py
```

Open:

- `http://localhost:3000`
- `http://localhost:3000/memory`
- `http://localhost:3000/graph`

The demo shows the full loop: local memories, raw notes, source pages, concept pages, backlinks, graph context, search, and MCP-ready retrieval.

Check the demo:

```bash
python3 link.py ingest-status .
python3 link.py doctor .
```

## First 10 Minutes

Use this path to turn one real note into local agent memory.

### 1. Create your wiki

From the cloned `link/` checkout, not `link-demo/`:

```bash
bash integrations/kiro/install.sh
```

Use the installer for your agent if it is not Kiro:

```bash
bash integrations/codex/install.sh
bash integrations/claude-code/install.sh
bash integrations/cursor/install.sh
bash integrations/copilot/install.sh
bash integrations/vscode/install.sh
bash integrations/antigravity/install.sh
```

This creates `~/link/`, installs or upgrades `link-mcp`, and writes lightweight agent instructions. Your wiki data is left alone on reinstall.

### 2. Add one source

```bash
cat > ~/link/raw/first-memory.md <<'EOF'
---
title: "First Link memory"
source_type: note
date_captured: 2026-05-04
---

# First Link memory

I am testing Link as local personal memory for agents.
Raw notes stay local. The agent turns them into source-cited wiki pages.
EOF
```

Check what is pending:

```bash
python3 ~/link/link.py ingest-status ~/link
```

### 3. Save one memory

Use direct memories for preferences, decisions, and project context future agents should recall:

```bash
python3 ~/link/link.py remember "I am testing Link as local personal memory for agents." ~/link --type preference --scope user --tags onboarding
python3 ~/link/link.py propose-memories "I prefer local, inspectable agent memory. We decided to keep Link local-first." ~/link
python3 ~/link/link.py recall "local personal memory" ~/link
python3 ~/link/link.py profile ~/link
python3 ~/link/link.py memory-inbox ~/link
python3 ~/link/link.py explain-memory prefer-local-personal-memory ~/link
python3 ~/link/link.py update-memory prefer-local-personal-memory "Also prefer updating existing memories over creating duplicates." ~/link
```

### 4. Ask your agent to ingest it

In your agent chat:

```text
ingest raw/first-memory.md into Link
```

The agent reads `~/link/LINK.md`, creates a source page under `wiki/sources/`, creates or updates concept/entity pages, updates `wiki/index.md`, appends `wiki/log.md`, and rebuilds backlinks.

### 5. Verify the loop

```bash
python3 ~/link/link.py doctor ~/link --fix
python3 ~/link/link.py ingest-status ~/link
python3 ~/link/link.py verify-mcp ~/link
```

Then ask your MCP-enabled agent:

```text
query Link for first Link memory
```

If the agent answers from Link, the local memory loop is working.

## Choose Your Path

### I want to try Link

Use the demo:

```bash
python3 link.py demo
cd link-demo
python3 serve.py
```

### I want my agent to use Link

Run the installer for your agent:

```bash
bash integrations/kiro/install.sh          # Kiro
bash integrations/claude-code/install.sh   # Claude Code
bash integrations/codex/install.sh         # Codex
bash integrations/cursor/install.sh        # Cursor
bash integrations/copilot/install.sh       # Copilot
bash integrations/vscode/install.sh        # VS Code
bash integrations/antigravity/install.sh   # Google Antigravity
```

For project-specific memory instead of global `~/link`, add `--project`.

To update after `git pull`, rerun the same installer. It refreshes code and instructions without replacing your wiki pages.

The installers try the current `python3` first. If that Python is externally managed, they install `link-mcp` into `~/.link-mcp-venv` and register MCP with that venv Python.

### I want MCP only

Install `link-mcp` and point it at a wiki:

```bash
python3 -m pip install --upgrade link-mcp
```

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

On macOS/Homebrew Python, if pip reports `externally-managed-environment`, use a dedicated venv:

```bash
python3 -m venv ~/.link-mcp-venv
~/.link-mcp-venv/bin/python -m pip install --upgrade pip link-mcp
```

Then use that Python in your MCP config:

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

### I want to develop or release Link

```bash
python3 -m unittest discover -s tests
python3 scripts/check_release_hygiene.py
python3 scripts/prepare_release.py 1.0.6 --dry-run
```

Release flow details are lower in this document.

## Core Concepts

| Concept | Meaning |
|---------|---------|
| `raw/` | Immutable sources: notes, papers, articles, transcripts, images, PDFs. |
| `wiki/` | Agent-maintained Markdown memory compiled from sources. |
| Source pages | One page per ingested source, stored under `wiki/sources/`. |
| Memory pages | Directly captured preferences, decisions, facts, and project context under `wiki/memories/`. |
| Concept/entity pages | Synthesized knowledge pages with source citations and confidence tags. |
| `_backlinks.json` | Reverse and forward link index used by search, graph, HTTP API, and MCP. |
| `log.md` | Append-only audit trail of ingest, query, lint, and maintenance operations. |

You curate sources and ask questions. The LLM writes and maintains the wiki.

## Daily Workflow

Add source material:

```bash
cp notes.md ~/link/raw/
python3 ~/link/link.py ingest-status ~/link
```

Ask your agent:

```text
ingest raw/notes.md into Link
```

Remember preferences and decisions directly:

```bash
python3 ~/link/link.py remember "User prefers release/* branches for Link work." ~/link --title "Prefer release branches" --type preference --scope project
python3 ~/link/link.py propose-memories ~/link/raw/session-notes.md ~/link
python3 ~/link/link.py recall "branch preference" ~/link
python3 ~/link/link.py profile ~/link
python3 ~/link/link.py memory-inbox ~/link
python3 ~/link/link.py review-memory prefer-release-branches ~/link --note "confirmed"
python3 ~/link/link.py explain-memory prefer-release-branches ~/link
python3 ~/link/link.py update-memory prefer-release-branches "Use release/* branches for public release work." ~/link
python3 ~/link/link.py archive-memory prefer-release-branches ~/link --reason "superseded"
python3 ~/link/link.py restore-memory prefer-release-branches ~/link
```

Maintain the wiki:

```bash
python3 ~/link/link.py doctor ~/link --fix
python3 ~/link/link.py rebuild-backlinks ~/link
python3 ~/link/link.py verify-mcp ~/link
```

View the wiki:

```bash
cd ~/link
python3 serve.py
```

Open `http://localhost:3000` or the memory dashboard at `http://localhost:3000/memory`.

Obsidian also works: open the `wiki/` folder as a vault.

## Local Commands

| Command | What it does |
|---------|-------------|
| `python3 link.py demo` | Create `./link-demo` with a pre-ingested sample wiki. |
| `python3 link.py ingest-status <dir>` | Show pending raw files and graph index status. |
| `python3 link.py remember "text" <dir>` | Save a local agent memory under `wiki/memories/`; strong duplicates are refused unless `--allow-duplicate` is set. |
| `python3 link.py propose-memories <file-or-text> <dir>` | Propose durable memories from notes without writing them. |
| `python3 link.py update-memory <name> "text" <dir>` | Merge new text into an existing memory, log it, rebuild backlinks, and reset review to pending. |
| `python3 link.py recall "query" <dir>` | Search local agent memories first. |
| `python3 link.py profile <dir>` | Show what Link remembers by type, scope, status, and recency. |
| `python3 link.py memory-inbox <dir>` | Show memories that need review or stronger metadata. |
| `python3 link.py review-memory <name> <dir>` | Mark a confirmed memory as reviewed. |
| `python3 link.py explain-memory <name> <dir>` | Explain provenance, lifecycle, graph links, review issues, and recall readiness for one memory. |
| `python3 link.py archive-memory <name> <dir>` | Reversibly hide a stale or wrong memory from default recall. |
| `python3 link.py restore-memory <name> <dir>` | Restore an archived memory to active recall. |
| `python3 link.py doctor <dir>` | Check structure, graph health, source hygiene, and secret-looking content. |
| `python3 link.py doctor <dir> --fix` | Create missing structure and repair backlinks safely. |
| `python3 link.py rebuild-backlinks <dir>` | Regenerate `wiki/_backlinks.json`. |
| `python3 link.py verify-mcp <dir>` | Verify `link-mcp` import and print MCP config. |

## MCP Server

Link is listed on the [official MCP Registry](https://registry.modelcontextprotocol.io/?q=io.github.gowtham0992%2Flink) as `io.github.gowtham0992/link`.

Available tools:

| Tool | Description |
|------|-------------|
| `memory_profile` | Summarize what Link remembers by type, scope, status, recent memories, preferences, decisions, and project context. |
| `memory_inbox` | List memories that need user review, cleanup, or stronger metadata. |
| `review_memory` | Mark a confirmed memory as reviewed. |
| `explain_memory` | Explain why a memory exists and whether it is ready for recall. |
| `search_wiki` | Ranked search by title, alias, tag, and full text. Returns scores and snippets. |
| `recall_memory` | Search durable local memory pages for preferences, decisions, and project context. |
| `remember_memory` | Save an explicit user-approved memory under `wiki/memories/`; strong duplicates require `allow_duplicate=true`. |
| `propose_memories` | Propose durable memories from chat/session notes without writing them. |
| `update_memory` | Merge new information into an existing memory and reset review to pending. |
| `archive_memory` | Archive stale or wrong memory without deleting the Markdown page. |
| `restore_memory` | Restore archived memory to active status. |
| `get_context` | Primary tool. Returns the best page plus inbound and forward graph neighbors. |
| `get_pages` | Lists pages with metadata. Filter by category, type, or maturity. |
| `get_backlinks` | Returns inbound and forward links for one page. |
| `get_graph` | Returns all nodes and edges for graph reasoning. |
| `rebuild_backlinks` | Rebuilds `_backlinks.json` after ingest or maintenance. |

Use `memory_profile` to inspect the user/project memory shape, then `recall_memory` when an answer depends on preferences, decisions, or project context. Use `get_context` for source-backed topic answers; it gives the agent the primary page plus its graph neighborhood in one call.

## HTTP API

`serve.py` exposes the same local memory over HTTP while the web viewer is running.

Local use only: `serve.py` binds to `127.0.0.1` and has no authentication. Do not expose it to the internet without adding auth. Memory write operations stay CLI/MCP-only; the HTTP proposal endpoint is analysis-only and does not write memory pages.

| Endpoint | Description |
|----------|-------------|
| `GET /api/pages` | All pages with title, type, tags, aliases, maturity, and TLDR. |
| `GET /api/memory-dashboard` | Read-only memory dashboard data: active, review queue, recent updates, archived, and next-action command hints. |
| `GET /api/memory-profile` | Counts and recent memories for the local memory profile. |
| `GET /api/memory-inbox` | Memories that need review or metadata cleanup. |
| `GET /api/explain-memory?memory=<name>` | Provenance, lifecycle, graph links, review state, and recall readiness for one memory. |
| `POST /api/propose-memories` | JSON `{ "text": "...", "source": "optional", "limit": 10 }`; returns memory proposals without writing pages. |
| `GET /api/search?q=<query>` | Ranked search by title, alias, tag, TLDR, and full text. |
| `GET /api/context?topic=<topic>` | Best matching page plus inbound and forward graph links. |
| `GET /api/graph` | Nodes and edges for graph visualization. |
| `GET /api/backlinks` | Reverse and forward link index. |
| `POST /api/rebuild-backlinks` | JSON `{}`; rebuild `_backlinks.json` by scanning wikilinks. |

Search uses an in-memory token index. `/api/context` is the main endpoint for agents that need a topic and its surrounding graph.

## Privacy And Safety

Link is local-first:

- No telemetry.
- No hosted backend.
- No external API calls from `serve.py` or `link-mcp`.
- Raw sources and generated wiki pages are ignored by git by default.
- Registry token files and common secret-looking files are ignored and checked by release hygiene.

Before sharing a repo, demo, or wiki:

```bash
python3 link.py doctor .
python3 scripts/check_release_hygiene.py
```

Treat `doctor` errors as blockers. Warnings usually mean quality work: missing summaries, missing source sections, stale source counts, isolated pages, or raw files not represented in source pages.

Use `git push`, `git archive`, or clean build artifacts for public sharing. Do not zip a whole working directory; ignored local files, `.git/`, caches, raw sources, and build outputs can be included by accident.

## Develop And Release

Run the local gate:

```bash
python3 -m unittest discover -s tests
python3 -m py_compile link.py serve.py scripts/check_release_hygiene.py scripts/prepare_release.py scripts/smoke_mcp_stdio.py mcp_package/link_mcp/server.py
python3 scripts/check_release_hygiene.py
bash -n integrations/*/install.sh integrations/*/uninstall.sh integrations/_shared/*.sh
python3 link.py demo /tmp/link-mcp-smoke --force
PYTHONPATH=mcp_package python3 scripts/smoke_mcp_stdio.py /tmp/link-mcp-smoke/wiki
git diff --check
```

Prepare release files:

```bash
python3 scripts/prepare_release.py 1.0.6
```

This bumps the MCP version files and moves `CHANGELOG.md` `Unreleased` notes into a dated version section.

After the release PR merges and CI passes:

```bash
git switch main
git pull --ff-only
git tag -a v1.0.6 -m "v1.0.6"
git push origin v1.0.6
cd mcp_package
python3 -c "from pathlib import Path; import shutil; shutil.rmtree('dist', ignore_errors=True); [shutil.rmtree(p, ignore_errors=True) for p in Path('.').glob('*.egg-info')]"
python3 -m build
python3 -m twine check dist/*
TWINE_USERNAME=__token__ python3 -m twine upload dist/*
mcp-publisher publish
```

Never reuse a published PyPI version or move a public release tag. If a release needs another fix, bump to the next version.

## Project Structure

```text
link/
├── LINK.md              # schema and instructions for agents
├── raw/                 # source documents, ignored by git
├── wiki/                # compiled knowledge, ignored by git except scaffolding
│   ├── index.md         # master catalog
│   ├── _backlinks.json  # reverse and forward link index
│   ├── log.md           # append-only operation history
│   ├── sources/         # one page per ingested source
│   ├── concepts/        # topic articles
│   ├── entities/        # people, orgs, projects
│   ├── comparisons/     # side-by-side analyses
│   └── explorations/    # filed query results
├── integrations/        # one-step setup per AI tool
├── mcp_package/         # PyPI package for link-mcp and shared link_core
├── scripts/             # release and hygiene tooling
├── serve.py             # local web viewer and HTTP API
└── link.py              # local utility CLI
```

## Design Principles

- Every claim links to a source.
- Confidence tags make uncertainty visible.
- `log.md` records wiki operations.
- Pages mature from seed to established.
- Agents should use `/api/context` or MCP `get_context` before reading files manually.
- The local web viewer has no runtime dependencies beyond Python stdlib.
- The wiki is plain Markdown, so it works with git, Obsidian, and normal editors.
