---
name: obsidian-processor
description: Organize an Obsidian vault in place. Files notes into PARA folders, names them from their content, adds frontmatter (description, category, tags, status, origin user/llm/mixed, created and modified dates, related notes), splits notes that mix topics into their own notes, archives older duplicates, fixes every wikilink after a rename, and keeps a Processing Log with one-step undo. Use whenever the user talks about their Obsidian vault or notes and says things like "process", "clean up", "file this", "triage my vault", "organize my notes", "sort my inbox", "update this note", "split this note", "tag these", or "undo the last run", even if they never name this skill. Needs file access to the vault (Claude Code, or Claude Desktop with Desktop Commander).
compatibility: Needs read/write access to the vault folder (Claude Code file tools or Desktop Commander) and Python 3.9+ on that machine; falls back to manual file edits without Python.
---

# Obsidian Processor

Keep the vault tidy with one request. Each run, Claude decides what every note
is about and where it belongs. `scripts/vault.py` then does the file work:
exact line cuts, renames, moves, link fixes, backups, the log, and undo.

The split exists because the user's words must survive untouched. Claude never
retypes note content. It hands the script line ranges, and the script moves
those bytes.

## Ground rules

1. **Never lose or paraphrase content.** Move text only through `splits` (line ranges). Change wording only when the user asked, and then only through `body_edits` / `insert_top`. This includes the first `# Heading`: leave it even when it no longer matches the new title. Say so once in the report, and offer "update the headings to match the titles" (done with `body_edits`).
2. **One living note per topic.** Filenames are titles. Never use `v2`, `final`, `copy` or `(1)`. A duplicate is superseded and archived, never kept alongside.
3. **The user's fields win.** Existing frontmatter values are kept. The script only adds keys, adds list items, and manages `modified` / `processed`.
4. **Never delete.** Superseded or dead notes go to `90-Archive`.
5. **Don't guess.** If a note's topic, folder, or which duplicate is current is unclear, leave it in `00-Inbox` with `status: draft` and add a question to the plan's `questions`.
6. **Leave a trail.** Every change lands in `99-Meta/Processing Log.md` and can be reversed with undo.
7. **Lead with the bottom line** in the report. No long explanations.

## Setup: find the vault and the tool

**Vault** = the folder that contains `.obsidian/`. If the user hasn't said where it is, look in the current directory, then ask once. Call it `VAULT` below.

**Tool** (`VP` below):
- **Claude Code**: the skill folder is on the same machine. Run `python3 <this skill>/scripts/vault.py`.
- **Claude Desktop with Desktop Commander**: this skill's files are in Claude's sandbox, not on the user's machine.
  1. Run `python3 "VAULT/.obsidian-processor/bin/vault.py" --version` with `start_process`.
  2. If it's missing or not `1.0.0`, read `scripts/vault.py` from this skill and `write_file` it to `VAULT/.obsidian-processor/bin/vault.py`.
  3. Run every command with `start_process`.
- **No Python** on the machine: follow `references/manual-mode.md`. It's the same plan, done by hand, and slower.

Every command prints JSON. Read `ok`, `errors` and `warnings` before moving on.

## First run (once per vault)

`VP scan VAULT --scope all --out VAULT/.obsidian-processor/scan.json` reports `"initialized": false` on a vault the skill hasn't seen.

1. Look at `top_folders`. Propose a folder map in one short message:
   - The default is the PARA set in `references/filing-rules.md`.
   - If the vault already has folders that play those roles (e.g. `Inbox`, `Archive`), map onto them instead of creating parallel ones.
2. After the user confirms, run `VP init VAULT`. Add `--config-json '{"folders": {"inbox": "Inbox", ...}}'` only for folders that differ from the defaults. This creates the folders, `99-Meta/Processing Log.md`, `99-Meta/Vault Dashboard.md`, and `.obsidian-processor/config.json`.
3. Carry on with the user's request from **Every run, step 1**, re-scanning with the scope it calls for.
4. In that first report, add the **First run** line (see Report) naming the folders created and the two optional plugins:
   - **Dataview**, which powers the dashboard.
   - **Update time on edit**, set to keys `created` / `modified`, which keeps dates current between runs.

After the first run, runs are automatic: file, rename and split without asking. Undo is the safety net.

## Every run

### 1. Scan the right scope

| User says | Command |
|---|---|
| "process / update / split *this note*" | `VP scan VAULT --paths "<note path>"` |
| "file my inbox", "sort my inbox" | `VP scan VAULT --scope inbox` |
| "triage my vault", "clean up", "organize my notes" | `VP scan VAULT --scope changed --out VAULT/.obsidian-processor/scan.json` |
| "undo the last run" / "undo run <id>" | skip to **Undo** |

`changed` returns only notes that need work: no frontmatter, or edited since last processed. Inbox drafts and daily notes that haven't changed don't come back. Use `--scope all` only when the user wants a full re-file.

Process **at most 25 notes per plan** (`apply` enforces this). Bigger triages run as several batches, one run id each.

The scan also returns the vault's existing `categories`, `tags`, `top_folders` and `category_folders`. Reuse them; don't invent near-duplicates (`kce` vs `KCE-ops`).

### 2. Decide, note by note

Read each note in full before deciding anything about it. For each one, decide:

| Field | How | Detail |
|---|---|---|
| `title` | What the note is about, Title Case, ≤ 60 chars. Omit the field to keep the filename. If the note has a `title:` property that differs from its filename, the user chose it: use it. A `title:` equal to the filename was written by the script and carries no weight. | `references/filing-rules.md` |
| `folder` | Projects / Areas / Reference / Archive / Inbox. A category gets a subfolder only once 3+ notes share it in that folder, counting this plan and its splits. `apply` warns below that. | `references/filing-rules.md` |
| `frontmatter.description` | One plain-English line saying what the note is for. | `references/frontmatter.md` |
| `frontmatter.category`, `tags` | One category and 2–5 tags, reusing the vault's vocabulary. Inbox drafts may skip the category. | `references/frontmatter.md` |
| `frontmatter.status` | `draft` (Inbox, unclear), `active`, `superseded`, `archived`. | `references/frontmatter.md` |
| `frontmatter.origin` | `user`, `llm`, `mixed`, or `unknown` when unsure. | `references/origin-detection.md` |
| `splits` | Only for notes with a second, unrelated topic. Run `VP outline VAULT "<note>"` and use its line numbers. | `references/splitting.md` |
| duplicates | Same topic in two notes: the newer one stays `active` with `supersedes`; the older one gets `status: superseded`, `superseded_by`, folder `90-Archive`. | `references/filing-rules.md` |
| `frontmatter.related` | After drafting the plan, run `VP related VAULT "<note>" ... --plan PLAN.json`. It scores the vault as it will be after the plan, including notes your splits create. Keep **up to 5** that a reader would actually want next. Fewer is fine; never pad. Unknown names fail the dry run. | `references/frontmatter.md` |

Leave these alone:
- **Daily notes** (`YYYY-MM-DD.md` or the Daily Notes folder): frontmatter only (`category: Journal`, `tags: [daily]` plus a topic tag or two). They are never renamed, moved or split.
- **Notes over 80% code/data** (`mostly_code: true`): frontmatter only, though they may be renamed and filed.
- **Notes with `processor: skip`**: leave them out of the plan.

Don't fill in `created`, `modified`, `processed`, `aliases` or `split_from`. The script sets them from file dates and the rename.

### 3. Write the plan

Write `VAULT/.obsidian-processor/plans/<YYYYMMDD-HHMM>.json`. The run manifest records which plan it came from.
- Shape: `assets/plan.schema.json`
- Example: `assets/plan-example.json`

Minimal entry:

```json
{"path": "kce notes final v2.md", "title": "KCE Ops Notes", "folder": "20-Areas",
 "frontmatter": {"description": "...", "category": "KCE", "tags": ["kce"], "status": "active",
                 "origin": "user", "related": ["Matrix Billing"]},
 "splits": [{"start": 15, "end": 23, "mode": "append", "target": "Fantasy Football"}],
 "summary": "Renamed, filed to Areas, fantasy football section moved out."}
```

Put anything you're unsure of in `"questions": ["..."]`. Each becomes a checkbox under **Needs you** in the log.

### 4. Dry run, then apply

```
VP apply VAULT PLAN.json --dry-run      # fix every error it lists, repeat until ok: true
VP apply VAULT PLAN.json                # backup → split → frontmatter → move/rename → fix links → log
```

Dry-run errors mean the plan is wrong: an unknown key, a bad title character, a name collision, a split through a code block, or a `related` name that matches nothing. Fix the plan, not the vault.

Read the warnings too (cleaned tags, a category respelled to the vault's existing one, a thin subfolder, a split below the size threshold). Each operation in the dry run shows the final `frontmatter` it will write; check `created`, `modified`, and that the user's values won.

Never rename or move notes with `mv`, `move_file` or Obsidian-unaware tools. `apply` rewrites every `[[link]]`, `![[embed]]`, `[[note#heading]]`, `[[note|alias]]` and relative markdown link across the vault. A plain move skips that.

### 5. Report

Use exactly this shape:

```
**Bottom line:** 13 notes processed · 11 filed · 2 split · 1 archived · 2 questions for you.
Undo: say "undo obsidian-processor run 20261113-140500".

| File | New title | Category | Status | Origin | Folder | Action | Reason |
|---|---|---|---|---|---|---|---|
| kce notes final v2.md | KCE Ops Notes | KCE | active | user | 20-Areas | renamed, split | version words in name; fantasy football is its own topic |
| *(new, from Obsidian Processor Skill Plan)* | RAG Pipeline litellm Prompt | RAG Pipeline | active | llm | 30-Reference/RAG Pipeline | created | pasted LLM prompt, different topic |
| 2026-11-01.md | 2026-11-01 | Journal | active | user | *(stays, daily note)* | frontmatter | daily notes never move |

**Needs you**
- What is [[Untitled 3]] about? (left in 00-Inbox)

**Changes**
- KCE Ops Notes: renamed, fantasy football section moved to [[Fantasy Football]].

**Health:** broken links 1 → 1 · missing frontmatter 11 → 0 · loose in root 12 → 0
**First run:** created 00-Inbox … 99-Meta, Processing Log, Vault Dashboard. Optional plugins: Dataview, Update time on edit.
```

Bottom-line counters, every one taken from `apply`'s `operations`:
- **processed**: notes in the plan plus notes the run created
- **filed**: notes whose folder changed, including moves into the Inbox or the Archive
- **split**: notes that gave up a section
- **archived**: notes newly marked `superseded`
- **questions**: the plan's `questions`

Links fixed in notes outside the plan go in **Changes**, not in the table.

The **Health** line comes from `VP check` run before and after. It's always there for a triage and optional for a single note.

The **First run** line appears only on the first run.

Finish with one line: *Full history: `99-Meta/Processing Log.md` (Ctrl/Cmd+O → "Processing Log").*

## Edit requests ("process: add a plain-English summary at the top")

Use the same flow, with the change expressed in the plan so it's backed up and undoable:
- `insert_top`: text added right under the frontmatter.
- `body_edits`: `[{"find": "exact text", "replace": "new text"}]`. Each `find` must occur exactly once.

Leave everything else in the note untouched. If you wrote new text into a note that was `user`, set `origin: mixed`.

## Undo

```
VP undo VAULT                 # latest run
VP undo VAULT --run <id>      # a specific run (later runs must be undone first)
```

Undo restores every original byte from `.obsidian-processor/backups/<id>.zip`, moves renamed notes back, and removes notes the run created.

If the user edited a note after the run, undo stops and lists those files. Tell the user, and only add `--force` if they agree to lose those edits.

## Health check

`VP check VAULT` counts broken links, duplicate names, notes missing frontmatter, and loose notes in the root. Run it before and after a big triage, and say in the report if the broken-link count went up. It shouldn't.

## Reference files

- `references/frontmatter.md`: every field, date rules, merge rules, tag/category vocabulary
- `references/filing-rules.md`: folders, subfolders, naming, duplicates, collisions
- `references/splitting.md`: how mixed notes are segmented, tested and split, with worked examples
- `references/origin-detection.md`: telling user, LLM and mixed writing apart
- `references/log-and-dashboard.md`: log format, dashboard queries, what the user sees
- `references/manual-mode.md`: doing a run without Python
- `assets/plan.schema.json`, `assets/plan-example.json`: plan format
