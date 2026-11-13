# Splitting notes that mix topics

Goal: every note covers one topic. When a second, unrelated topic is inside a note (fantasy football in the KCE note, a litellm prompt pasted under an Obsidian plan), that part moves to the note where someone would look for it. It moves **word for word**, and a link is left where it was.

## How it works

1. **Segment.** Run `vault.py outline VAULT "<note>"`. It prints **sections** (heading to the end of that section) and **blocks** (paragraphs, lists, tables, quotes, chat turns, code fences), all with file line numbers. A code fence is always one block. The script refuses a split that cuts through one.

2. **Label.** Read the note and give each block a topic, using the vault's categories where possible. Ask: *what would someone search for to find this block?*

3. **Group.** Merge neighbouring blocks with the same topic into runs. The **primary topic** is the one that matches the title, or failing that the one with the most lines. It stays.

4. **Test each other run.** Split it out only if **all three** hold:
   - its topic is *different* from the primary topic: a different category, or a subject with its own name, not a sub-point;
   - it's big enough: **≥ 8 lines or ≥ 15% of the note** (`split_min_lines` / `split_min_share` in config);
   - a reader looking for that topic would *never* think to open this note.

   Anything that fails stays put. If it's a real aside, add the matching tag instead.

5. **Choose the destination.**
   - If a note on that topic exists (check `scan.all_notes` and `related`), use `mode: append` and `target: <that note>`. The block lands at the end under `> [!info] Moved here from [[Parent]] — <date>`. This keeps one living note per topic.
   - Otherwise use `mode: new` with a `title`, a `folder`, and the segment's *own* `frontmatter`. In particular, give it its own `origin`; a pasted LLM answer inside a user note is `llm`. The script adds `split_from: [[Parent]]` and copies the parent's `created`.

6. **The trail.** The cut lines become one line in the parent:
   `> [!note] Moved to [[Fantasy Football]] — 2026-11-13`.
   Blank lines around it are kept, so the callout never swallows the next paragraph.

7. **Verification is automatic.** Before writing anything, `apply` checks that every moved block appears byte for byte in its destination. If not, nothing is written.

Range rules: `start`/`end` are **file** line numbers from `outline`, inclusive. They must be below the frontmatter, inside the file, not overlapping, and not cutting through a code fence. Include the section heading in the range when the whole section moves. Leading and trailing blank lines in the range are kept in the parent.

## Worked examples

**Fantasy football inside the KCE note** (append):
```
outline:  L15-L23  ## Fantasy football
          (the rest of the note is billing, closeout, follow-ups)
test:     different topic ✓ · 9 lines ✓ · nobody looks for draft picks in "KCE Ops Notes" ✓
plan:     {"start": 15, "end": 23, "mode": "append", "target": "Fantasy Football"}
result:   KCE Ops Notes  → "> [!note] Moved to [[Fantasy Football]] — 2026-11-13"
          Fantasy Football → "> [!info] Moved here from [[KCE Ops Notes]] — 2026-11-13" + the 9 lines
```

**An LLM prompt pasted under a plan** (new note, different origin):
```
note:     "Create plan for new skill generation- organize obsidian.md" (193 lines)
          L1-L120   the user's goals + the draft skill plan       → primary topic, stays
          L121-L193 "Your generator.py already calls litellm…"    → RAG pipeline prompt
test:     different topic ✓ · 73 lines ✓ · not findable under "Obsidian Processor Skill Plan" ✓
plan:     {"start": 121, "end": 193, "mode": "new", "title": "RAG Pipeline litellm Prompt",
           "folder": "30-Reference/RAG Pipeline",
           "frontmatter": {"category": "RAG Pipeline", "origin": "llm", ...}}
parent:   renamed "Obsidian Processor Skill Plan", origin mixed
```
There's no heading at L121, so use the **blocks** list to find where the topic changes.

**Python chat vs file-type chunking notes:** a chat about Python in general, with one long answer about chunking file types for the RAG parser:
- The chunking answer is its own topic (RAG Pipeline, not general Python), and it's long. If "RAG File Types and Embedding" exists, append it there. Otherwise make a new note.
- A two-line "also, use pathlib" aside stays; it's under 8 lines and still about Python.

## When **not** to split

- Sub-points of one topic: "Billing" and "Closeout" inside a KCE note are both KCE.
- Short asides (< 8 lines and < 15%): tag them instead.
- Notes over 80% code/data, daily notes, and `processor: skip` notes. The script refuses these anyway.
- When you can't name the second topic with confidence. Ask in `questions` instead.
