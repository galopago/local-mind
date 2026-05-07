# Security Policy

## Local-first threat model

Link is designed for local personal knowledge management. `serve.py` binds to
`127.0.0.1`, rejects host/bind flags, and rejects unexpected `Host` headers
outside `localhost`/`127.0.0.1`. It has no authentication, so it should not be
exposed directly to the public internet.

The server and MCP package do not call external APIs, send telemetry, or require
secrets. Raw sources and generated wiki pages are user data and are ignored by
git by default.

`link ingest-status` and MCP `ingest_status` scan raw source files locally for
secret-looking values. If a pending raw file is flagged, Link withholds the
normal ingest prompt until the file is redacted.

## Sensitive files

Do not commit:

- `raw/` source files
- generated wiki pages under `wiki/sources/`, `wiki/concepts/`,
  `wiki/entities/`, `wiki/comparisons/`, or `wiki/explorations/`
- `.mcpregistry_*`
- `*.token`
- build outputs under `mcp_package/dist/`

Use `git status --ignored` before release if you want to inspect local-only
files, and use `git archive` or normal GitHub releases rather than zipping a
working directory.

## Reporting vulnerabilities

Please report security issues through GitHub issues or private maintainer
contact channels. Avoid posting secrets, private wiki content, or raw source
files in public reports.
