# Integrations

One-step setup for your AI tool. Default is global — one central wiki at `~/link/` that works across all projects.

## Quick start

```bash
git clone https://github.com/gowtham0992/link.git ~/link-repo
bash ~/link-repo/integrations/kiro/install.sh
```

That's it. Kiro now knows about Link in every project, and your wiki lives at `~/link/`.

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

1. Writes a small instruction file for your tool (so it knows Link exists)
2. Scaffolds wiki structure at `~/link/` (or current dir with `--project`)
3. Installs or upgrades `link-mcp` using normal pip first, then `~/.link-mcp-venv` if system Python is externally managed

The instruction file is minimal — it just tells the agent that Link exists and to read `LINK.md` when you say "ingest", "query", "lint", or "research". It doesn't interfere with normal coding work.

## Uninstall

Each folder has an `uninstall.sh`. Same `--project` flag applies.
