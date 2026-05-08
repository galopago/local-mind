<p align="center">
  <img src="logo.svg" alt="Link" width="120">
</p>

# Link

**Local, source-backed memory for LLM agents.**

Link gives Codex, Claude, Cursor, Kiro, VS Code, Copilot, and other MCP clients
the same durable memory about you and your work. The memory stays on your
machine as plain Markdown, with sources, backlinks, graph context, review state,
and an audit trail you can inspect.

It follows Andrej Karpathy's
[LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f):
keep knowledge outside the chat window, make claims inspectable, and let context
compound over time.

[![GitHub](https://img.shields.io/github/stars/gowtham0992/link?style=flat)](https://github.com/gowtham0992/link)
[![CI](https://github.com/gowtham0992/link/actions/workflows/ci.yml/badge.svg)](https://github.com/gowtham0992/link/actions/workflows/ci.yml)
[![MCP Registry](https://img.shields.io/badge/MCP_Registry-io.github.gowtham0992%2Flink-blue)](https://registry.modelcontextprotocol.io/?q=io.github.gowtham0992%2Flink)
[![PyPI](https://img.shields.io/pypi/v/link-mcp)](https://pypi.org/project/link-mcp/)

[Product site](https://gowtham0992.github.io/link/) ·
[First 10 minutes](https://gowtham0992.github.io/link/getting-started.html) ·
[MCP setup](https://gowtham0992.github.io/link/mcp.html) ·
[CLI reference](https://gowtham0992.github.io/link/cli.html) ·
[Security](SECURITY.md) ·
[Changelog](CHANGELOG.md)

<p align="center">
  <img src="docs/assets/link-demo-flow-dark.gif" alt="Link demo flow: wiki, memory dashboard, graph, and memory explanation" width="860">
</p>

## Why Link

Most agent sessions start from zero. You re-explain preferences, repo decisions,
project constraints, and why something matters. Link turns that repeated context
into local memory agents can query.

- **Personal memory:** preferences, decisions, facts, and project context carry
  across sessions.
- **Source-backed wiki:** raw notes become readable Markdown pages with citations
  and backlinks.
- **MCP-native recall:** every local agent can use the same memory layer.
- **Budgeted context:** smart query packets return useful context without
  flooding the model.
- **Private by default:** no hosted backend, no telemetry, no cloud lock-in.
- **Inspectable:** Markdown files, backlinks, logs, backups, and review states
  stay on your machine.

## Quick Start

Run the finished demo first. It already has raw sources, wiki pages, one starter
memory, backlinks, graph data, and query packets ready to inspect.

```bash
git clone https://github.com/gowtham0992/link.git
cd link
python3 link.py demo
python3 link.py serve link-demo
```

Open:

- `http://localhost:3000`
- `http://localhost:3000/brief`
- `http://localhost:3000/memory`
- `http://localhost:3000/audit`
- `http://localhost:3000/captures`
- `http://localhost:3000/propose`
- `http://localhost:3000/graph`

Then try:

```bash
python3 link.py query "why does Link help agents?" link-demo --budget small
python3 link.py brief "working on agent memory" link-demo
python3 link.py benchmark "agent memory" link-demo
python3 link.py status --validate link-demo
```

The first query should return a compact packet with relevant memory, the best
wiki page, graph context, provenance, and follow-up actions. The demo also
writes `link-demo/START_HERE.md` with prompts and checks to try.

The generated demo is the public proof wiki. The repo's root `wiki/` directory
is only a scaffold for local development and personal testing; generated content
inside `wiki/`, `raw/`, and `link-demo/` is ignored by git so personal memory is
not published by accident.

The demo includes one pending memory on purpose so you can see the review inbox,
explain-memory view, and audit trail. Mark it reviewed when you want a clean
memory-audit state.

## Install Paths

### I Want To Try Link

Use the demo:

```bash
python3 link.py demo
python3 link.py serve link-demo
```

Then follow the [First 10 minutes guide](https://gowtham0992.github.io/link/getting-started.html).

### I Want My Agent To Use Link

Run the installer for your agent from the cloned checkout:

```bash
bash integrations/codex/install.sh
bash integrations/kiro/install.sh
bash integrations/claude-code/install.sh
bash integrations/cursor/install.sh
bash integrations/copilot/install.sh
bash integrations/vscode/install.sh
bash integrations/antigravity/install.sh
```

Installers create or update `~/link`, install or upgrade `link-mcp`, write
lightweight agent instructions, and preserve existing wiki data on reinstall.
Use `--project` for repo-local memory.

### I Want MCP Only

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

On macOS/Homebrew Python, if pip reports `externally-managed-environment`, use a
dedicated venv:

```bash
python3 -m venv ~/.link-mcp-venv
~/.link-mcp-venv/bin/python -m pip install --upgrade pip link-mcp
```

Full setup: [MCP guide](https://gowtham0992.github.io/link/mcp.html).

## What Users Actually Do

Link has one simple rule:

```text
Sources become wiki knowledge.
Explicit "remember" becomes agent memory.
Queries use both.
```

Use these moves with your agent:

```text
is Link ready?
brief me from Link before we continue
ingest raw/notes.md into Link
remember that I prefer short release notes
query Link for the release process
what does Link remember about local personal memory?
```

Or use the local command:

```bash
link prompts
link ingest-status
link remember "I prefer short release notes." --type preference --scope user
link brief "working on a release"
link query "what should I know before changing the MCP tools?" --budget small
link validate
```

## What You Get

### Wiki Home

Browse pages by type, search locally, and open the same Markdown pages your
agents use.

<p align="center">
  <img src="docs/assets/link-home-dark.png" alt="Link wiki home in dark mode" width="860">
</p>

### Memory Dashboard

See what agents can remember, what needs review, and what changed recently.

<p align="center">
  <img src="docs/assets/link-memory-dashboard-dark.png" alt="Link Memory Dashboard in dark mode" width="860">
</p>

### Knowledge Graph

Inspect relationships between sources, concepts, entities, explorations, and
memories. Large graphs open as bounded overviews first, with filters, search,
neighborhood depth, and explicit full-graph loading when needed.

<p align="center">
  <img src="docs/assets/link-graph-dark.png" alt="Link Knowledge Graph in dark mode" width="860">
</p>

### Explain Memory

Every memory can explain why it exists, whether it is review-ready, and what
source or log evidence supports it.

<p align="center">
  <img src="docs/assets/link-explain-memory-dark.png" alt="Link Explain Memory view in dark mode" width="860">
</p>

## Agent Contract

Link's agent workflow is intentionally small and predictable. Agents should start
with readiness, then use compact query and memory packets before reaching for
larger graph/context tools:

| Tool | Use it when |
|------|-------------|
| `link_status` | Check setup, content counts, search backend, warnings, and safe next actions. |
| `starter_prompts` | Show the user exactly what to ask after install. |
| `ingest_status` | Inspect pending raw files and the safest next ingest prompt. |
| `query_link` | Build one compact answer-ready packet from memory, wiki search, graph context, and provenance. |
| `memory_brief` | Prime an agent before longer work. |
| `get_graph_summary` | Fetch bounded graph context without dumping every node and edge. |
| `backup_wiki` | Create a local archive before broad repair work. |
| `validate_wiki` | Verify page shape, links, and backlink freshness after ingest or large edits. |

Full MCP tool list: [MCP guide](https://gowtham0992.github.io/link/mcp.html).

## Privacy And Safety

Link is local-first:

- No telemetry.
- No hosted backend.
- No external API calls from `serve.py` or `link-mcp`.
- Raw sources and generated wiki pages are ignored by git by default.
- `link backup` excludes `raw/` unless you explicitly pass `--include-raw`.
- Secret-looking values are detected in raw sources, captures, and release
  hygiene checks.
- The local web server binds to `127.0.0.1` and is not meant to be exposed to
  the internet without additional auth.

Before sharing a repo, demo, or wiki:

```bash
python3 link.py doctor
python3 link.py validate
python3 scripts/check_release_hygiene.py
```

More detail: [Security guide](https://gowtham0992.github.io/link/security.html).

## Docs

| Need | Go here |
|------|---------|
| Run Link for the first time | [First 10 minutes](https://gowtham0992.github.io/link/getting-started.html) |
| Understand raw/wiki/memory | [Concepts](https://gowtham0992.github.io/link/concepts.html) |
| Configure MCP | [MCP setup](https://gowtham0992.github.io/link/mcp.html) |
| Find a command | [CLI reference](https://gowtham0992.github.io/link/cli.html) |
| Use local HTTP endpoints | [HTTP API](https://gowtham0992.github.io/link/api.html) |
| Review security boundaries | [Security model](https://gowtham0992.github.io/link/security.html) |
| Contribute | [Contributing](https://gowtham0992.github.io/link/contributing.html) |
| Fix setup issues | [Troubleshooting](https://gowtham0992.github.io/link/troubleshooting.html) |

## Contributing

Contributions should come through pull requests. Please target `main` unless the
maintainer asks for a different branch. The `develop` branch is a maintainer
integration branch for staging larger release work before it is proposed to
`main`.

Before opening a PR, run:

```bash
python3 -m ruff check .
python3 -m unittest discover -s tests
python3 scripts/check_release_hygiene.py
python3 scripts/check_runtime_duplication.py
python3 scripts/check_tool_contract.py
git diff --check
```

Full contributor guide: [Contributing](https://gowtham0992.github.io/link/contributing.html).

Do not include personal wiki data, raw sources, registry tokens, `.env` files, or
local MCP credentials in a PR.
