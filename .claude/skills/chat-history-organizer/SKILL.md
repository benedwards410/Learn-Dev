---
name: chat-history-organizer
description: Use when Nonya says 'organize my chats', 'index my chat history', 'triage my chats', or 'update the chat index' — builds/updates a Chat Index of past Claude chats and artifacts, with rename and new-project suggestions.
---

# Chat History Organizer

Build and maintain a **Chat Index**: a filing system for past Claude chats and artifacts, with links back to each one.

**Limits (flag in one line on first run only, then proceed):**
- Claude cannot rename, move, edit, or split chats, or create projects. The index suggests; Nonya acts.
- Chat search only sees the current scope: outside a project = non-project chats; inside a project = that project only.
- Claude Code sessions cannot be indexed.
- Only last-updated dates are available, not created dates.
- Must remain local. Sensitive info containing PII should not be shared outside of users files.

## Trigger
- "organize my chats", "index my chats", "triage my chat history", "update the chat index"
- Optional scope: date range ("last 2 weeks"), topic ("KCE chats"), or "everything"
- "save a local copy" → also write to a folder on her computer (see Local copy)

## Steps
1. **Find the index.** List artifacts for an existing "Chat Index". If found, update it. Never create a second one.
2. **Detect scope.** Outside a project → Project column = "None". Inside a project → Project column = that project's name. Each project run appends to the same index.
3. **Gather chats.** recent_chats (paginate with `before`, max ~5 calls; say if coverage is incomplete) or conversation_search for a topic scope. Skip chats already indexed unless updated_at is newer than the row.
4. **Read only what's needed.** Snippet first. read_conversation only when the topic is unclear or the chat looks mixed. One page per chat.
5. **Classify each chat** (Index columns). If a chat covers unrelated topics, create **one row per topic segment** sharing the same link, with a segment note (e.g. "2nd half: fantasy football").
6. **Find related chats.** conversation_search 2–3 distinctive terms per row; link up to 3 related chats by indexed title.
7. **Index artifacts.** list_artifacts (own artifacts); classify each into the Artifacts tab.
8. **Suggest projects.** Apply the Project Suggestions rule.
9. **Write the sheet** (Sheets artifact type; .xlsx only if she asks). Append a Log row.
10. **Local copy** if asked (see below).
11. **Report:** bottom line first — "X chats added, Y updated, Z artifacts, N project suggestions, M need a call." Then the link. No recap.

## Tab 1 — Chats
| Column | What goes in it |
|---|---|
| Title | Clean, descriptive, no "v2/final" |
| Rename to | Paste-ready chat name (≤ 50 chars). Blank if current name is already good |
| Description | One plain-English line |
| Folder | See list below |
| Project | Project name, or "None" |
| Tags | 2–5 tags |
| Type | Build · Research · Draft · Brain dump · Q&A · Planning |
| Last updated | From updated_at |
| Segment note | Only for split chats |
| Related chats | Up to 3, by indexed title |
| Link | Chat URL |

**Folders:** KCE Ops · KCE Builds/Apps · Baseball & Youth Sports · Research · Personal & Family · Finance · Inbox (unclear)

## Tab 2 — Artifacts
| Title | Artifact type (Doc, Sheet, Slides, Design, Dashboard, Page…) | Description | Folder | Tags | Last updated | Related chats | Link |
|---|---|---|---|---|---|---|---|

## Tab 3 — Project Suggestions
**Rule:** 3+ chats (or 2 chats + 1 artifact) on the same topic with Project = "None" → one suggestion.

| Column | What goes in it |
|---|---|
| Suggested project name | Short, plain |
| Join existing instead? | Name an existing project if one fits; otherwise "New" |
| Chats to move | Linked titles |
| Related artifacts | Linked titles |
| Starter instructions | 3–5 lines of project instructions drawn from the chats |
| Status | Suggested · Done · Skip (Nonya edits) |

Don't re-suggest rows she marked Skip.

## Tab 4 — Log
| Date | Scope run | Chats added | Updated | Split | Artifacts | Project suggestions | Inbox count |
|---|---|---|---|---|---|---|---|

Note at top of the Log tab:
"Ask Claude 'update the chat index' to refresh. Run it inside each project to add that project's chats. Filter by Folder or Tags to find a chat; tap Link to open it. Copy 'Rename to' into the chat's menu to rename."

## Local copy (optional)
- When asked and the desktop app is connected with a folder: write `Chat Index.xlsx` (all tabs) and `Chat Index.md` (Chats + Project Suggestions as tables) to the folder she names.
- If the folder is an Obsidian vault: write `Chat Index.md` with frontmatter (title, description, updated, tags) and one `[[wikilink]]`-free table — links stay as URLs.
- If not connected: say so in one line and offer the .xlsx download from the sheet.

## Rules
- Unsure of folder → Inbox, with the question in Description. Don't guess.
- Don't overwrite Folder, Tags, Rename to, or Status that she edited by hand.
- Titles describe content, not the chat's auto-name.
- No info about minors in titles, descriptions, tags, or project names — describe by activity only (e.g. "12U fundraiser plan").
- Keep output terse. Lead with counts.

## Examples
- **"organize my chats from this month"** → ~20 chats indexed, 2 split, 8 rename suggestions, 1 project suggestion ("KCE Supplier Sourcing", 4 chats), 3 in Inbox; counts + link.
- **"update the chat index"** (run inside the BGE SBSE Projects project) → that project's new/changed chats appended with Project = "BGE SBSE Projects".
- **"index my chats and save a local copy to my vault"** → sheet updated + `Chat Index.md` written to the vault folder.

## Not possible
- Renaming, moving, editing, or splitting actual chats; creating projects
- Seeing all projects in one run
- Claude Code sessions
- Created dates
- Auto-run on every new chat (a weekly scheduled task can run it instead)
