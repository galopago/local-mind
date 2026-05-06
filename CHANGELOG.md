# Changelog

All notable changes to Link are tracked here.

Release sections use `MAJOR.MINOR.PATCH` versions that match `link-mcp` on PyPI and the MCP Registry. Keep `Unreleased` for work merged after the latest published version.

## [Unreleased]

### Added

- Added Memory Mode foundation with `wiki/memories/`, `link.py remember`, `link.py recall`, and MCP `remember_memory`/`recall_memory` tools.
- Added a first-run demo memory page so Link presents as local agent memory, not only a wiki.
- Added Memory Profile views through `link.py profile`, MCP `memory_profile`, `/profile`, and `/api/memory-profile`.
- Added reversible memory lifecycle controls with `archive-memory`/`restore-memory` and MCP `archive_memory`/`restore_memory`; archived memories are hidden from recall by default.
- Added confirmed permanent memory deletion with `forget-memory` and MCP `forget_memory` for user-requested local forgetting.
- Added low-priority forget actions to memory review/explanation payloads so permanent deletion is discoverable but never the default next step.
- Added memory action commands to web inbox and explanation pages, including review, update, archive, restore, and low-priority forget actions.
- Added Memory Review Inbox with `memory-inbox`, `review-memory`, MCP `memory_inbox`/`review_memory`, `/inbox`, and `/api/memory-inbox`.
- Added Explain Memory views with `explain-memory`, MCP `explain_memory`, `/explain-memory`, and `/api/explain-memory` for provenance, review state, lifecycle, graph links, and recall readiness.
- Added `/propose`, a read-only local UI for turning pasted source/session notes into memory proposals without writing pages.
- Added MCP `link_status` and `/api/status` for a compact readiness summary with version, wiki path, page/memory counts, optional validation, and safe next actions.
- Added `link.py status` so the same readiness summary is available before MCP or the local web server is connected.
- Added `link.py status --validate` to installer next-step output so new users have one readiness command after setup.
- Added a managed `~/.local/bin/link` command for global installs so users can run `link status --validate`, `link query`, and `link brief` without remembering wiki paths.
- Added `link init` to create or repair a normal Link wiki without loading demo content.
- Added `link serve` to start the local web viewer without remembering `serve.py` paths.
- Added wiki schema markers with safe `link migrate`/MCP `migrate_wiki` migrations for future local format changes.
- Added first-run agent prompts to installer output so new users can immediately try brief, remember, and query workflows.
- Added guided `link ingest-status` output with structured JSON guidance, exact agent prompts, and follow-up validation commands.
- Added `/ingest` and `/api/ingest-status` so the local UI shows pending raw files, graph health, and the next agent prompt.
- Added clearer product framing in the README and local home page for the distinction between source-backed wiki knowledge and explicit agent memory.
- Added a local raw-source picker to `/propose` with secret-aware loading for proposal-only memory workflows.
- Added a wider graph page layout with fullscreen mode so larger wikis can be explored without being squeezed into the reading column.
- Added large-graph controls for node search, type filtering, and selected-node neighborhood depth.
- Added duplicate protection for `remember`/`remember_memory`; strong duplicate memories are refused unless explicitly allowed.
- Added memory merge/update workflow with `update-memory` and MCP `update_memory`, including update counts, audit logs, backlink rebuilds, and review reset.
- Added proposal-only memory extraction with `propose-memories` and MCP `propose_memories` for chat/session notes.
- Added agent memory briefs with `link.py brief` and MCP `memory_brief` so agents can prime themselves with relevant local memory before a task.
- Added smart Link query packets with `link.py query`, MCP `query_link`, and `/api/query-link` so agents can retrieve budgeted memory, ranked wiki results, and graph context without reading the whole wiki.
- Added smart query budget reports and follow-up tool actions so agents know when context was truncated and how to continue without scanning the whole wiki.
- Added `link.py validate` as an ingest gate for agent-generated wiki pages, covering required frontmatter, type/directory alignment, required sections, dead links, and stale backlinks.
- Added MCP `validate_wiki` and `/api/validate` so agents can run the same ingest gate without shell access.
- Added a runtime duplication guard in CI to block new large copied helper bodies across CLI, web, and MCP runtimes.
- Added raw capture status to CLI and MCP memory briefs so session priming surfaces saved captures and secret-warning captures.
- Added `/brief` and `/api/memory-brief` so the local web UI and HTTP clients can get startup memory context, review warnings, and raw capture status.
- Added `memory-audit` and MCP `memory_audit` for a read-only health report covering memory backlog, raw captures, risk factors, and next actions.
- Added `/audit` and `/api/memory-audit` so the local web UI exposes the same read-only memory audit report.
- Added memory review and raw capture backlog checks to `link.py doctor`, while excluding proposal-only raw captures from ingest-status pending source counts.
- Added conflict detection for memory writes, updates, and proposals; contradictory active memories are surfaced before saving unless explicitly allowed.
- Added shared memory review action plans so inbox and explanation payloads tell agents whether to review, update, archive, restore, or edit metadata next.
- Added project-aware memory boundaries so project-scoped memories can carry a project key and recall/profile/brief keep other explicit projects out of context.
- Improved memory recall ranking so project-matched and reviewed memories win ties while archived/stale memories rank lower when explicitly included.
- Added `link.py capture-session` to save long session notes under `raw/memory-captures/` and return proposal-only memory candidates for human approval.
- Added MCP `capture_session` so agents can preserve long session notes locally before asking which memory proposals to write.
- Added secret-looking content warnings to CLI and MCP session capture results so pasted tokens can be redacted from local raw notes.
- Added `link.py accept-capture` to turn an approved raw-capture proposal into a durable memory through duplicate/conflict-safe writes.
- Added MCP `accept_capture` for approving saved capture proposals through the same duplicate/conflict-safe workflow.
- Added `link.py redact-capture` to replace secret-looking values in saved raw captures while logging only warning labels and counts.
- Added MCP `redact_capture` so agents can redact saved raw captures after user approval.
- Added `link.py delete-capture` with explicit confirmation for removing saved raw captures without logging capture contents.
- Added MCP `delete_capture` with explicit confirmation for removing saved raw captures.
- Added `link.py capture-inbox` to list saved raw captures, secret warnings, and accept/redact/delete commands.
- Added MCP `capture_inbox` to review saved raw captures with redacted snippets before accepting, redacting, or deleting them.
- Added raw capture visibility to `/memory` and `/api/memory-dashboard`, including accept/redact/delete commands and secret-warning counts.
- Added `/captures` and `/api/capture-inbox` for a dedicated local web/API raw capture inbox.
- Added project filtering to `/memory`, `/profile`, `/api/memory-dashboard`, `/api/memory-profile`, and `/api/memory-inbox`.
- Added project filtering to CLI and MCP memory inbox workflows.
- Added read-only web Memory Dashboard at `/memory` and `/api/memory-dashboard` for active memories, review queue, recent updates, archived memories, and next-action commands.
- Added recall readiness metadata to recalled memories so CLI, MCP, and brief payloads expose whether memory is ready, provisional, unsafe, or disabled.
- Added local web review/archive/restore memory actions backed by guarded HTTP POST endpoints; permanent forget remains command/tool-only.
- Added secure proposal-only HTTP endpoint `POST /api/propose-memories`; HTTP memory mutations are limited to local review/archive/restore actions.
- Added a graph node inspector so moving nodes no longer accidentally opens pages; double-click or Open page still navigates.
- Added an explicit `system`/`dark`/`light` theme toggle for the local web UI; dark mode now uses a black page background.
- Added a real MCP stdio smoke test for the built `link-mcp` wheel in CI.
- Added release hygiene checks that protect the public agent instruction contract for `query_link`, `validate_wiki`, and `memory_brief`.
- Updated agent contract checks and installed instructions to include `link_status` for setup/readiness checks.
- Changed CI to run on pull requests and manual dispatch only, preserving GitHub minutes for the develop-branch workflow.
- Added CLI validation to the CI demo health smoke path so PRs catch broken generated wiki templates.
- Updated the PyPI package README with the current MCP tool contract, validation workflow, capture inbox, and permanent-forget guidance.
- Updated package classifiers and PR CI coverage for modern Python, including Python 3.14.
- Added Memory Dashboard next actions so the web UI and API surface the most important memory maintenance step.
- Extracted shared memory proposal logic into `link_core` so CLI, HTTP, and MCP proposal behavior stays aligned.
- Extracted shared raw capture path resolution and notes parsing into `link_core` so CLI and MCP capture operations use the same root-escape guard.
- Extracted shared frontmatter parsing and typed update helpers into `link_core` for safer memory metadata writes.
- Extracted shared memory record loading, review inbox, profile, and recall helpers into `link_core`.
- Extracted shared memory resolution, log lookup, and recall-state helpers into `link_core`.
- Extracted shared memory lifecycle mutations for archive, restore, review, and update workflows into `link_core`.
- Extracted shared memory creation for `remember` and `remember_memory` into `link_core`.
- Extracted shared wiki indexing, search, context, graph, and backlink helpers into `link_core`.
- Extracted shared memory explanation/audit payloads into `link_core`.

### Fixed

- Tightened README onboarding and release examples around Link's local memory product value.
- Simplified onboarding docs and installed instructions around natural agent prompts and the short `link` command instead of path-heavy maintenance commands.
- Moved the local UI theme control into a compact header utility above search so it no longer wraps awkwardly in the navigation row.
- Reworked the local UI header into a clean brand/tools row with navigation tabs below it.
- Fixed installer MCP setup reporting so failed upgrades no longer masquerade as success by reusing an unrelated older global `link-mcp`.
- Fixed project-mode installer output so MCP wiki paths are absolute and next-step hints point at the project wiki instead of `~/link`.
- Fixed search/context matching for natural queries against hyphenated page slugs, e.g. `local first software` now finds `local-first-software`.
- Hardened backlink rebuild over HTTP so local web rebuilds require JSON POST instead of a mutating GET.
- Hardened `/raw/` static serving so the local web viewer only serves supported media/PDF source assets.
- Tightened raw asset path resolution so `/raw/` URLs cannot route through non-raw static allowlists, including encoded parent-directory paths.
- Hardened HTTP memory mutation endpoints with an explicit `X-Link-Local-Action: true` header required by non-UI clients.
- Refreshed the checked-in demo backlink index so `link.py doctor .` reports a healthy graph.

## [1.0.7] - 2026-05-04

### Fixed

- Fixed Codex MCP auto-registration after the venv installer fallback so existing `~/.codex/config.toml` files are updated without a regex crash.
- Fixed `link.py verify-mcp` to use the installer-recorded MCP Python when present.
- Fixed dashboard polish and search keyboard submission in the local web viewer.

## [1.0.6] - 2026-05-04

### Added

- Added `scripts/prepare_release.py` to bump MCP release versions, cut changelog notes, and print publish commands without uploading anything automatically.
- Added versioned changelog tracking for repo, PyPI, and MCP Registry releases.
- Added `link.py ingest-status` to show pending raw sources and stale graph indexes.
- Added `link.py doctor --fix` for safe structure creation and backlink repair.
- Added `link.py verify-mcp` to validate local MCP readiness and print client config.
- Added first 10 minutes onboarding docs.
- Added golden demo snapshot tests and direct MCP contract tests.

### Changed

- Moved raw capture inbox parsing, project filtering, snippet redaction, and command generation into shared `link_core.capture` helpers.
- Polished the graph view with reset, label, and motion controls, keyboard focus, empty-state handling, cursor-centered zoom, and sticky dragged node placement.
- Restructured README.md into a product-doc flow: promise, quick start, first 10 minutes, install paths, then reference and release details.
- Switched release guidance to `release/*` branches and made changelog updates part of the release checklist.
- Refreshed the Link logo.
- Improved first-run and Homebrew/PEP 668 install documentation.
- Narrowed CI trigger noise to pull requests, `main` pushes, and manual dispatch.

### Fixed

- Hardened installers to avoid silently using `--break-system-packages`; they now fall back to `~/.link-mcp-venv` and register MCP with the resolved Python.
- Hardened the local viewer against unsafe graph JSON embedding, path-like wikilink targets, malformed static paths, and local path leakage from static file errors.
- Hardened `link-mcp` tool inputs for empty queries/topics and invalid search limits.
- Expanded `doctor` and release hygiene checks for common credential filenames, private keys, and token patterns.

## [1.0.5] - 2026-05-02

### Added

- Added `link.py demo` for a pre-ingested sample wiki.
- Added `link.py doctor` health checks for structure, backlinks, source hygiene, graph integrity, and secret-looking files.
- Added CI release gates for tests, demo health, installer syntax, package build, version consistency, and release hygiene.

### Changed

- Published `link-mcp` 1.0.5 package metadata for PyPI and the MCP Registry.

### Fixed

- Fixed `/api/context` and MCP context handling for the current backlink index shape.
- Fixed markdown rendering so raw HTML and unsafe markdown links cannot execute in the browser.
- Fixed installers so reruns preserve existing user instructions and project installs point MCP at the project wiki.
- Fixed wiki cache invalidation so edits to existing pages refresh search and context.
- Fixed MCP package reinstall behavior so rerunning installers upgrades `link-mcp`.
- Fixed invalid HTTP search limits to return controlled JSON errors.

## Earlier

- `1.0.2` through `1.0.4` were early public MCP packaging and hardening releases. Use `1.0.5` or newer for public installs.
