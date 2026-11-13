# Log, dashboard and state

## What the user sees in Obsidian

**`99-Meta/Processing Log.md`** is written by `vault.py`. Never hand-edit it during a run.

```markdown
# Processing Log

> [!info] How to use this log
> - Every obsidian-processor run adds a section below (newest first) ...
> - Open it any time with Ctrl/Cmd + O → "Processing Log", or bookmark it ...
> - Needs you lists questions the skill would not guess ...
> - To reverse a run, tell Claude "undo obsidian-processor run <run id>" ...

## Needs you
- [ ] (20261113-140500) What is [[Untitled 3]] about: a call to return, or something to buy?

<!-- obsidian-processor: runs below, newest first -->

## 2026-11-13 14:05 — run 20261113-140500 (13 notes)

| Time | Action | Note | From → To | Summary |
|---|---|---|---|---|
| 14:05 | created | [[RAG Pipeline litellm Prompt]] | new: `30-Reference/RAG Pipeline/...` | litellm prompt split out of the skill plan |
| 14:05 | moved, renamed, split | [[KCE Ops Notes]] | `kce notes final v2.md` → `20-Areas/KCE Ops Notes.md` | fantasy football moved to [[Fantasy Football]] |

Undo: tell Claude "undo obsidian-processor run 20261113-140500".
```

**Actions** you'll see:

| Action | Meaning |
|---|---|
| created | new note made by a split |
| split | a section moved out of this note |
| appended | received a section from another note |
| moved | changed folder |
| renamed | changed filename |
| superseded | marked as replaced by a newer note |
| edited | `insert_top` / `body_edits` applied |
| frontmatter | only properties changed |
| links | a `[[link]]` to a renamed or moved note was updated |
| restored / removed | an undo |

The `summary` you write in the plan becomes the Summary column, so make it a short, human sentence. Questions from `questions` land under **Needs you** as checkboxes. If the user answers in chat, process the note and tell them they can tick the box.

**`99-Meta/Vault Dashboard.md`** is created once by `init` and never overwritten. It holds Dataview tables: recently processed, waiting in the Inbox, by category, written by an LLM (or partly), split out of other notes, superseded. Without the Dataview plugin it shows the raw queries. Mention the plugin once on the first run.

How to tell the user to find these: **Ctrl/Cmd + O**, type "Processing Log" or "Vault Dashboard". Suggest bookmarking both (right-click the tab → Bookmark).

## Hidden state: `.obsidian-processor/`

Obsidian ignores dot-folders, so none of this shows up in search or the graph.

| Path | What |
|---|---|
| `config.json` | folder names, category vocabulary, excludes, split thresholds, batch size |
| `plans/<stamp>.json` | the plans Claude wrote (useful for auditing a run) |
| `runs/<run id>.json` | manifest: every file created, modified or moved, with the hash written |
| `backups/<run id>.zip` | the original bytes of every file the run changed |
| `bin/vault.py` | the tool copy, when running through Desktop Commander |

Undo uses the manifest and the backup:
- It refuses if a later run is still active.
- It refuses if a file changed after the run. `--force` overrides, but only with the user's OK.
- It never deletes a created note that the user has since edited.
- The log keeps the history and gets an "undo of run …" section.
