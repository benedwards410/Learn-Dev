# Frontmatter

Every processed note starts with this block (Obsidian shows it as Properties):

```yaml
---
title: KCE Ops Notes
description: How KCE bills Matrix, closes out jobs, and what to follow up on.
category: KCE
tags:
  - kce
  - operations
status: active
origin: user
created: 2026-03-02
modified: 2026-10-30
related:
  - "[[Matrix Billing]]"
  - "[[Contractors]]"
aliases:
  - kce notes final v2
supersedes: "[[Older Note]]"          # only when it applies
superseded_by: "[[Newer Note]]"       # only when it applies
split_from: "[[Parent Note]]"         # only on notes created by a split
processed: 2026-11-13T14:05
---
```

## Who sets what

| Key | You put it in the plan? | Rule |
|---|---|---|
| `title` | yes (or omit) | Defaults to the final filename. If the note already has a `title`, the user's value is kept and you should name the file after it. If the old `title` just mirrored the old filename, the script updates it on rename. |
| `description` | **yes** | One plain-English line, ≤ 140 characters, saying what the note is *for*. Start with a noun or verb, not "This note…". |
| `category` | **yes** | Exactly one, Title Case. Reuse a category from `scan.categories` whenever one fits. A new category is fine when nothing fits; then it's part of the vocabulary. |
| `tags` | **yes** | 2–5, lowercase, kebab-case, no `#`. Nested tags are fine (`kce/billing`). Reuse `scan.tags`. Don't repeat the category as a tag unless the vault already does. Tags are only ever added, never removed. |
| `status` | **yes** | `draft` (unclear / Inbox), `active`, `superseded`, `archived`. An existing user value is kept, except that the script moves `draft → active` when you file the note and always applies `superseded` / `archived`. |
| `origin` | **yes** | `user`, `llm`, `mixed`, `unknown`. See `origin-detection.md`. |
| `related` | **yes** | 3–5 note names (plain names; the script turns them into `"[[links]]"` using final names). Shortlist with `vault.py related … --plan PLAN.json`. Added to what's already there. |
| `supersedes` / `superseded_by` | for duplicates | Note names. The script makes them links. |
| `created` | no | Script: existing `created` (or `date created` / `created_at` / `date`) → otherwise the earliest of file birth time, modified time, and any `YYYY-MM-DD` in the filename. |
| `modified` | no | Script: today if the body changed in this run. Otherwise the date of the user's last real edit (file mtime), not the date the skill added frontmatter. |
| `aliases` | no | Script adds the old filename on rename (skipped for "Untitled N" and case-only renames), so search and autocomplete still find the old name. |
| `split_from` | no | Script sets it on notes created by a split. |
| `processed` | no | Script stamps date and time (minutes) on every note it changed. A note edited after this stamp shows up in the next `--scope changed` scan. |

Any other key in `frontmatter` is added only if the note doesn't already have it.

## Merge rules (why the user's YAML survives)

The script edits frontmatter line by line; it does not re-serialize it:
- **Existing keys keep their lines, order and formatting**, unless the key is `modified`, `processed` or `superseded_by`, or a list key that gains items.
- **List keys** (`tags`, `aliases`, `related`) gain new items at the end; existing items stay. If items are added, that one key is rewritten in block style.
- **New keys** are appended at the end in the order above.
- A note that only *looks* like it has frontmatter (it starts with a `---` horizontal rule) is treated as having none. Real frontmatter is added above it.

## Dates

- ISO dates (`2026-11-13`) so Obsidian and Dataview read them as dates.
- `processed` is `YYYY-MM-DDTHH:MM`.
- Obsidian doesn't update `modified` on its own. Recommend the **Update time on edit** community plugin with keys `created` and `modified`, so dates stay right between runs.

## Vocabulary hygiene

- Before inventing a category or tag, check `scan.categories` and `scan.tags` for a near match (`fantasy football` vs `fantasy-football`, `KCE` vs `Kce Ops`). Use the existing spelling.
- If the user keeps a fixed list, it lives in `.obsidian-processor/config.json` under `categories`. Stay inside it, and ask before adding to it.
