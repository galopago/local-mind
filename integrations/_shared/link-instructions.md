## Link — Local Agent Memory

Local agent memory lives at `~/link/`. It has raw sources in `~/link/raw/`, compiled wiki pages in `~/link/wiki/`, and direct memories in `~/link/wiki/memories/`.

If you are unsure whether Link is ready, use MCP `link_status` when available, or run `link status --validate`.

If status reports a missing or old schema marker, use MCP `migrate_wiki` when available, or run `link migrate`, before other writes.

When answering a substantive question that may need local memory or wiki context, start with MCP `query_link` when available, or run `link query "<task or question>"`.

When starting personalized or project-specific work, prime yourself with Link first: use MCP `memory_brief` when available, or run `link brief "<task or question>"`.

After ingesting raw sources or making substantial wiki edits, use MCP `rebuild_backlinks` and `validate_wiki` when available, or run `link rebuild-backlinks` and `link validate`, before saying the wiki is updated.

When the user says **"remember"**, **"recall"**, **"ingest"**, **"query"**, **"lint"**, or **"research"**, read `~/link/LINK.md` for instructions and follow the protocol. Use terminal commands to access `~/link/` since it's outside the workspace.

Otherwise, don't interfere — just be a normal assistant.
