# Use obsidian-processor

Talk to Claude normally. These phrases do the work.

| You say | What happens |
|---|---|
| "triage my vault" | Every new or edited note gets processed, 25 at a time |
| "file my inbox" | Just `00-Inbox` and loose notes in the root |
| "process *Note*" | One note |
| "process *Note*: add a summary at the top" | Adds the summary; the rest stays word for word |
| "merge *A* into *B*" | A's unique parts move into B; A is archived |
| "undo the last run" | Every file goes back exactly as it was |

## Where notes go

| Folder | Holds |
|---|---|
| `00-Inbox` | topic unclear, waiting for you |
| `10-Projects` | has a goal and an end |
| `20-Areas` | ongoing, no end date |
| `30-Reference` | look-up knowledge |
| `90-Archive` | superseded; never deleted |
| `99-Meta` | the log and dashboard |

## What a run does

1. **Scan**: finds notes that are new or edited since the last run.
2. **Decide**: Claude reads each note and picks its title, folder, tags, origin and any splits.
3. **Dry run**: catches bad names, collisions and broken links before anything moves.
4. **Apply**: backs up, then splits, tags, renames, moves and fixes every link.
5. **Report**: bottom line, table, questions, undo command.

## A note before and after

`kce notes final v2.md` becomes `20-Areas/KCE Ops Notes.md`:

```yaml
---
description: How KCE bills Matrix, closes out jobs, and what to follow up on.
category: KCE
tags: [kce, operations, billing]
status: active
origin: user
created: 2026-10-30
related: ["[[Matrix Billing]]", "[[Contractors]]"]
aliases: [kce notes final v2]
---
# KCE notes
...
> [!note] Moved to [[Fantasy Football]] — 2026-11-13
```

## In Obsidian

- **Ctrl/Cmd + O → "Processing Log"**: every change, newest first, plus the **Needs you** checklist.
- **Ctrl/Cmd + O → "Vault Dashboard"**: notes by status, category and origin, and recent runs.
- Keep a note out of it: add `processor: skip` to its properties.
- Answer a question by telling Claude, or edit the note; it comes back on the next triage.
