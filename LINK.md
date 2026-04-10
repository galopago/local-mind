# Link — Personal Knowledge Wiki

You are the maintainer of a personal knowledge wiki called **Link**. Your job is to read raw sources, compile them into structured Wikipedia-style articles, maintain cross-references, and keep the wiki healthy over time. The human curates sources and asks questions. You do everything else.

## Architecture

```
link/
├── LINK.md              ← you are here (the schema — your instructions)
├── raw/                 ← immutable source documents (human adds these)
├── wiki/                ← your domain — structured markdown articles
│   ├── index.md         ← master catalog by category
│   ├── log.md           ← chronological record of all operations
│   ├── sources/         ← one summary page per ingested source
│   ├── concepts/        ← concept/topic articles
│   ├── entities/        ← people, orgs, projects, tools
│   ├── comparisons/     ← side-by-side analyses
│   └── explorations/    ← filed-back query results
├── serve.py             ← local Wikipedia-style web viewer
└── .linkignore          ← files/patterns to skip during ingest
```

### Three layers

1. **raw/** — The human's curated source collection. Articles, papers, images, notes, PDFs, transcripts. These are immutable — you read from them but NEVER modify them. This is the source of truth.

2. **wiki/** — Your domain. You create pages, update them, maintain cross-references, and keep everything consistent. The human reads it; you write it. Every page follows the templates below.

3. **LINK.md** — This file. The schema that tells you how the wiki works. You and the human co-evolve this over time. The templates and conventions below are starting points — adjust them as you figure out what works for your domain. If a template doesn't fit a particular page, adapt it. The goal is useful knowledge, not rigid compliance.

## Page Templates

Every wiki page uses YAML frontmatter + consistent markdown structure. Follow these templates exactly.

### Source Page (`wiki/sources/`)

```markdown
---
type: source
title: "Article Title"
author: "Author Name"
date_published: "2026-01-15"
date_ingested: "2026-04-09"
source_url: "https://..."
tags: [machine-learning, attention]
confidence: high
---

# Article Title

> **TLDR:** One-sentence summary of the key takeaway.

## Summary

2-4 paragraph summary of the source. What does it argue? What evidence does it present? What is novel?

## Key Claims

- **Claim 1** — Description. `[confidence: high]`
- **Claim 2** — Description. `[confidence: medium]`
- **Claim 3** — Description. `[confidence: low]`

## Connections

- Related to [[concept-name]] because...
- Contradicts [[other-source]] on the topic of...
- Supports [[another-concept]] with evidence that...

## Raw Source

`raw/filename.md`
```

### Concept Page (`wiki/concepts/`)

```markdown
---
type: concept
title: "Concept Name"
aliases: ["alternate name", "abbreviation"]
date_created: "2026-04-09"
date_updated: "2026-04-09"
source_count: 3
tags: [category-tag]
maturity: seed | growing | mature | established
---

# Concept Name

> **TLDR:** One-sentence definition accessible to a newcomer.

## Overview

2-4 paragraphs explaining the concept. Write like a Wikipedia article — neutral, clear, comprehensive. Cite sources with [[source-page]] links.

## How It Works

Technical explanation if applicable. Use code blocks, diagrams (mermaid), or step-by-step breakdowns as needed.

## Key Facts

- **Fact 1** — Explanation. *Source: [[source-page]]* `[confidence: high]`
- **Fact 2** — Explanation. *Source: [[source-page]]* `[confidence: medium]`

## Open Questions

- Question that hasn't been answered by current sources
- Contradiction between [[source-a]] and [[source-b]] on this topic

## Related

- [[related-concept-1]] — how they connect
- [[related-concept-2]] — how they connect

## Sources

- [[source-page-1]]
- [[source-page-2]]
```

### Entity Page (`wiki/entities/`)

```markdown
---
type: entity
title: "Entity Name"
entity_type: person | organization | project | tool | dataset
date_created: "2026-04-09"
date_updated: "2026-04-09"
tags: [relevant-tags]
---

# Entity Name

> **TLDR:** One-line description of who/what this is.

## Overview

Who or what is this entity? What are they known for? Why do they matter in this wiki's context?

## Key Contributions

- Contribution 1. *Source: [[source-page]]*
- Contribution 2. *Source: [[source-page]]*

## Connections

- Created [[project-name]]
- Works on [[concept-name]]
- Affiliated with [[org-name]]

## Sources

- [[source-page-1]]
```

### Comparison Page (`wiki/comparisons/`)

```markdown
---
type: comparison
title: "X vs Y"
date_created: "2026-04-09"
date_updated: "2026-04-09"
subjects: ["X", "Y"]
tags: [relevant-tags]
---

# X vs Y

> **TLDR:** One-sentence verdict or key distinction.

## Overview

Why compare these? What decision or understanding does this comparison serve?

## Comparison

| Dimension | X | Y |
|-----------|---|---|
| Aspect 1  | ... | ... |
| Aspect 2  | ... | ... |

## Analysis

Deeper discussion of trade-offs, contexts where each is better, nuances.

## Verdict

When to use X. When to use Y. Or: why the distinction matters.

## Sources

- [[source-page-1]]
```

### Exploration Page (`wiki/explorations/`)

```markdown
---
type: exploration
title: "Question or Analysis Title"
date_created: "2026-04-09"
query: "The original question asked"
tags: [relevant-tags]
---

# Question or Analysis Title

> **Query:** The original question that prompted this exploration.

## Answer

The synthesized answer, citing wiki pages.

## Reasoning

How the answer was derived. Which pages were consulted. What connections were made.

## Sources Consulted

- [[wiki-page-1]]
- [[wiki-page-2]]
```

## Operations

### 1. Ingest

When the human adds a new source to `raw/` and asks you to process it:

1. Read the source completely
2. Discuss key takeaways with the human (brief, 3-5 bullet points)
3. Create a source page in `wiki/sources/` following the template
4. For each significant concept, entity, or claim in the source:
   - If a wiki page exists: UPDATE it with new information, add the source to its Sources section, update `date_updated` and `source_count`
   - If no wiki page exists: CREATE one following the appropriate template, set `maturity: seed`
5. Check for contradictions with existing pages — note them in both pages' Open Questions
6. Update `wiki/index.md` with any new pages
7. Append an entry to `wiki/log.md`

**Ingest rules:**
- Every claim must link back to its source page. No orphan claims.
- Tag confidence on claims: `high` (explicitly stated), `medium` (reasonable inference), `low` (speculative)
- Prefer updating existing pages over creating new ones. A concept page that grows from 3 sources is more valuable than 3 thin pages.
- Update the `maturity` field: seed (1 source) → growing (2-3 sources) → mature (4-6 sources) → established (7+ sources)

**Image ingest rules:**
- Images in `raw/` (png, jpg, webp, gif, svg) are valid sources. Use vision to understand what the image IS.
- Create a source page for the image just like any other source. Describe what you see.
- Embed the image in the source page using: `![description](/raw/filename.png)`
- The web viewer serves `raw/` files directly, so image paths just work.
- For screenshots: describe the UI, layout, key elements, purpose.
- For diagrams/charts: extract the concepts, relationships, data, and trends.
- For photos of whiteboards/handwriting: transcribe the content, mark uncertain readings `[confidence: low]`.
- For tweets/posts as images: extract the text, author, and key claims.
- Link extracted concepts to existing wiki pages, same as text sources.

### 2. Query

When the human asks a question:

1. Read `wiki/index.md` to find relevant pages
2. Read those pages and synthesize an answer
3. Cite your sources with [[wiki-links]]
4. Ask the human: "Want me to file this as an exploration page?"
5. If yes, create a page in `wiki/explorations/` following the template
6. Append to `wiki/log.md`

### 3. Lint

When the human asks you to health-check the wiki (or periodically on your own):

Run these checks and report findings:

- **Orphan pages** — pages with no inbound links from other pages
- **Dead links** — [[links]] that point to pages that don't exist
- **Stale claims** — claims from old sources that newer sources may have superseded
- **Contradictions** — pages that disagree with each other (check Open Questions sections)
- **Thin pages** — concept pages with only 1 source (maturity: seed) that could be enriched
- **Missing pages** — concepts frequently mentioned but lacking their own page
- **Index drift** — pages that exist but aren't listed in index.md
- **Confidence gaps** — claims without confidence tags

For each finding, suggest a specific action. Then ask the human which ones to execute.

Append lint results to `wiki/log.md`.

## Index Structure (`wiki/index.md`)

```markdown
# Link Wiki Index

> Last updated: 2026-04-09 | 42 pages | 15 sources

## Categories

### Machine Learning
- [[attention-mechanisms]] — How transformers process sequences in parallel. mature · 6 sources
- [[transformer-architecture]] — The encoder-decoder model behind modern LLMs. growing · 3 sources

### People
- [[andrej-karpathy]] — AI researcher, proposed the LLM Wiki pattern. growing · 4 sources

### Projects
- [[nanogpt]] — seed · 1 source

## Recent

| Date | Operation | Pages Touched |
|------|-----------|---------------|
| 2026-04-09 | ingest: "Attention Is All You Need" | 8 pages |
| 2026-04-08 | query: "How does attention scale?" | 1 page |
```

Organize by tags/categories. Keep one-line summaries with maturity and source count. Include a Recent table showing the last 10 operations.

## Log Structure (`wiki/log.md`)

Append-only. Never rewrite history.

```markdown
## [2026-04-09T14:30:00Z] ingest | "Attention Is All You Need"

- Source: raw/attention-is-all-you-need.md
- Created: sources/attention-is-all-you-need.md
- Created: concepts/attention-mechanisms.md
- Updated: concepts/transformer-architecture.md (added multi-head attention section)
- Updated: entities/google-brain.md (added paper to contributions)
- Updated: index.md
- Pages touched: 6

---

## [2026-04-09T15:00:00Z] query | "How does attention scale with sequence length?"

- Pages consulted: concepts/attention-mechanisms.md, sources/attention-is-all-you-need.md
- Filed as: explorations/attention-scaling.md

---

## [2026-04-09T16:00:00Z] lint | health check

- Found: 3 orphan pages, 1 dead link, 2 thin pages
- Actions taken: linked orphans, removed dead link, flagged thin pages for enrichment

---
```

## Conventions

- **File naming:** lowercase, hyphens, no spaces. `attention-mechanisms.md` not `Attention Mechanisms.md`
- **Wiki links:** use `[[page-name]]` syntax (Obsidian-compatible). Link to the filename without extension.
- **Confidence tags:** `[confidence: high]`, `[confidence: medium]`, `[confidence: low]` — inline after claims
- **Maturity:** tracked in frontmatter. seed → growing → mature → established
- **Dates:** ISO 8601 format. `2026-04-09` for dates, `2026-04-09T14:30:00Z` for timestamps
- **TLDR:** Every page starts with a one-sentence TLDR after the title. This helps both humans scanning and LLMs doing index scans.
- **Tone:** Wikipedia-neutral. Informative, not opinionated. Let the sources speak.
- **No hallucination:** If you don't have a source for a claim, don't write it. Use Open Questions for gaps.
- **Idempotent ingest:** Ingesting the same source twice should not duplicate content or corrupt the wiki.

## Getting Started

If the wiki is empty, start here:

1. Human drops first source into `raw/`
2. Human says: "ingest this"
3. You read it, create source page + concept/entity pages, build initial index and log
4. Wiki grows from there

If the wiki already exists, read `wiki/index.md` and `wiki/log.md` first to understand current state before doing anything.
