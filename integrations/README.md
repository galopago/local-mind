# Link Integrations

One-step setup for local agents. The default mode creates one central Link wiki
at `~/link/` and teaches your agent how to use it as local personal memory.

## Quick start

```bash
git clone https://github.com/gowtham0992/link.git ~/link-repo
bash ~/link-repo/integrations/codex/install.sh
```

Pick the installer that matches your agent. After install, try:

```text
is Link ready?
brief me from Link before we continue
query Link for what you know about this project
```

## All integrations

| Tool | Command | Global location |
|------|---------|----------------|
| Kiro | `bash integrations/kiro/install.sh` | `~/.kiro/steering/link.md` |
| Claude Code | `bash integrations/claude-code/install.sh` | `~/.claude/CLAUDE.md` |
| Antigravity | `bash integrations/antigravity/install.sh` | `~/.gemini/GEMINI.md` |
| Codex | `bash integrations/codex/install.sh` | `~/AGENTS.md` |
| Cursor | `bash integrations/cursor/install.sh` | `~/.cursor/rules/link.mdc` |
| Copilot | `bash integrations/copilot/install.sh` | `.github/copilot-instructions.md` |
| VS Code | `bash integrations/vscode/install.sh` | `.vscode/settings.json` |

## Two modes

- **Default (global):** `bash install.sh` — installs tool instructions globally + scaffolds central wiki at `~/link/`. One wiki for everything.

- **Project-local:** `bash install.sh --project` — installs instructions in current project + scaffolds wiki here. For team projects that need their own wiki.

## What the install does

1. Upserts a small Link instruction block without overwriting your existing instructions.
2. Scaffolds wiki structure at `~/link/` or the current directory with `--project`.
3. Installs or upgrades `link-mcp`, using `~/.link-mcp-venv` when system Python is externally managed.
4. Writes `.link-mcp-python` so clients can use the Python that actually has `link-mcp`.
5. Adds `~/.local/bin/link` for global installs, so checks are short: `link health`.
6. Prints next prompts and verification commands for your install mode.

The instruction file is intentionally small. It tells the agent to check
`link_status`, use `query_link` for compact context, use `memory_brief` before
personalized/project work, validate after ingest, and read `LINK.md` only when it
needs the full local protocol.

## Uninstall

Each folder has an `uninstall.sh`. Same `--project` flag applies.
