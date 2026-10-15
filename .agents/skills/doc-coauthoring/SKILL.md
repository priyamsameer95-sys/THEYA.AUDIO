---
name: doc-coauthoring
description: Structured collaborative technical writing methodology for specifications, architecture RFCs, disaster recovery plans, and runbooks.
---

# Collaborative Technical Document Co-authoring

A phased writing methodology designed to produce crisp, publication-ready technical specifications, runbooks, and disaster recovery plans without fluff or AI filler.

## The Co-authoring Sequence

```
[1. Transfer Context] ──► [2. Build Outline] ──► [3. Validate Structure] ──► [4. Draft Section-by-Section] ──► [5. Polish]
```

### 1. Transfer Context
- Gather raw architecture decisions, constraints, stakeholder requirements, and technical context before drafting.
- Explicitly identify the target audience (e.g. on-call engineers, external API developers, executive leadership).

### 2. Build Outline
- Author a structural skeleton containing only section headers and 1-2 bullet points summarizing the purpose of each section.
- Avoid writing prose during the outline phase.

### 3. Validate Structure
- Confirm the outline covers all necessary scenarios, edge cases, failure modes, and recovery workflows before writing prose.

### 4. Section-by-Section Drafting
- Draft one section at a time.
- Use direct, active voice ("Configure the proxy timeout to 15s" rather than "It is recommended that the timeout should be configured").
- Emphasize tables, mermaid diagrams, and numbered procedural steps over walls of text.

### 5. Final Polish
- Review against the anti-filler checklist:
  - Remove generic introductory platitudes ("In today's fast-paced digital world...").
  - Ensure all code snippets and shell commands are copy-paste executable.
  - Verify all internal references and links resolve.
