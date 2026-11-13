# Filing and naming

## Folders (PARA, renamable in `.obsidian-processor/config.json`)

| Folder | Put a note here when… | Examples |
|---|---|---|
| `00-Inbox` | you can't tell what it's about or where it goes. Status `draft` + a question. | "call back re: the thing tuesday" |
| `10-Projects` | it serves a goal with an end: a build, a job, a trip, an event. | "Obsidian Processor Skill Plan", one install job |
| `20-Areas` | it's an ongoing responsibility or interest with no end date. | "KCE Ops Notes", "Fantasy Football", "Reading List" |
| `30-Reference` | it's knowledge to look up later: how-tos, snippets, prompts, research. | "RAG File Types and Embedding", "RAG Pipeline litellm Prompt" |
| `90-Archive` | it's superseded, finished, or dead. Never delete; archive. | older duplicate, closed project |
| `99-Meta` | never: the skill's own log and dashboard live here. | |

Decide in this order: **superseded/finished → Archive**, **has an end → Projects**, **ongoing → Areas**, **look-up → Reference**, **unsure → Inbox**.

### Subfolders

One level, named after the category, e.g. `30-Reference/RAG Pipeline/`. This is a rule, not a suggestion: create one only when **3 or more notes** in that top folder share the category, counting this plan *and* the notes its splits create.
- `scan.category_folders` gives the counts before the plan.
- `apply --dry-run` warns when a subfolder would end up with fewer than 3.
- Below 3, the notes stay directly in the top folder.

Never nest deeper than `Top/Category/`.

### Never moved

- Daily notes: `YYYY-MM-DD.md`, or anything in the Daily Notes folder from `.obsidian/daily-notes.json`. The Daily Notes plugin looks for them there.
- The template folder (`.obsidian/templates.json`), `.obsidian/`, `.trash/`, other dot-folders, `99-Meta/`.
- Notes with `processor: skip`.
- Non-markdown files (images, PDFs, canvases).

## Names

The filename is the title, and the title is what the note is *about*:
- **Title Case**, 2–6 words, ≤ 60 characters: "KCE Ops Notes", "RAG Pipeline litellm Prompt".
- **No version words**: `v2`, `final`, `copy`, `(1)`, `new`, `old`, `latest`. There is one living note per topic. `vault.py` rejects the hard ones and warns on the soft ones.
- **No link-breaking characters**: `# | ^ : % [ ] / \ * " < > ?`. Write "Python - Chunking", not "Python: Chunking".
- Keep the user's own title if the note has a `title` property, or if the filename is already a good title. Renaming isn't the goal; findability is.
- Leave junk names ("Untitled 3") alone when the topic is unclear. The note waits in the Inbox with a question.
- Daily notes keep their date name.

### Collisions

Obsidian resolves `[[links]]` by filename, so final names must be unique across the whole vault (case-insensitive). On a collision, make the title more specific, e.g. "Python (RAG)" or "Billing (Matrix)", never "Python 2". `vault.py apply --dry-run` lists every collision.

If two notes would swap names in one run, do it as two runs.

## Duplicates and overlap

**Detect:** `vault.py related` scores near-identical notes at the top. Confirm by reading both. The same headings or the same lists mean they're duplicates.

**Pick the current one:**
1. The one that contains everything the other has plus more (a content superset) wins.
2. Otherwise the most recent real edit wins (`modified`, else `mtime` in the scan).
3. If neither is clearly current, ask. Leave both in place and put the question in `questions`.

**Then:**
- The current note: `status: active`, `supersedes: <older>`, filed normally (often renamed to a better title).
- The older note: `status: superseded`, `superseded_by: <current>`, `folder: 90-Archive`. Keep its title unless it has version words.

**Merge** happens only if the user says "merge". Move the older note's *unique* section(s) into the current note with a split (`mode: append`, `target: <current>`), then supersede the older note as above. Nothing is retyped, and nothing is deleted.

## Scopes and batches

- `--scope changed`: notes with no frontmatter, and notes edited since `processed`. Inbox drafts and daily notes come back only when they've been edited. Use `--scope inbox` to revisit the Inbox on purpose.
- At most 25 notes per plan (`apply` refuses more). For a 300-note first triage, run batches and report each batch's bottom line, then a final total.
- A note already processed and unchanged needs no entry. If you include it anyway with the same values, `apply` reports "nothing to change".
