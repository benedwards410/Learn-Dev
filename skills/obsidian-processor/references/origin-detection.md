# Origin: who wrote this note?

`origin` answers "how was this created?": `user`, `llm`, `mixed`, or `unknown`. It lets the user filter AI-written material (the dashboard has a view for it) and trust their own notes differently.

## Signals

| Points to **LLM** | Points to **user** |
|---|---|
| Chat-turn markers: "You said:", "ChatGPT said:", "Assistant:", "**User:**" | Typos and slips ("snd", "face" for "date") |
| Offers and closers: "Say go.", "Let me know if…", "I can build these files…", "Happy to help" | Shorthand, fragments, lowercase, missing punctuation |
| Openers: "Certainly!", "Great question", "Here's a…", "Below is…" | Personal context: names, dates, "I have the 4th pick" |
| ALL-CAPS spec sections (CONTEXT / REQUIREMENTS / OUTPUT / EXAMPLES) | Inconsistent formatting, half-finished lists |
| Uniform bold lead-ins, perfectly parallel bullets, a summary paragraph at the end | Questions to self ("blue one?"), reminders, todo checkboxes |
| Explaining to *you* what *you* should do: "Replace the model string with…" | First-person plans: "need to", "ask about" |
| Model-ish disclaimers, or "as an AI" | Copied data without commentary is neutral; use the surrounding text |

No single signal decides it. Look for two or more pointing the same way.

## Rolling up

1. Label each block from `outline` as user, llm, or unclear.
2. Roll up:
   - all user → `user`
   - all llm → `llm`
   - a meaningful share of both (each ≥ ~15% of the lines, or a clearly pasted answer inside the user's own notes) → `mixed`
   - not enough signal either way, e.g. short neutral notes or pure code → `unknown`
3. Split-out notes get their **own** origin. A pasted LLM answer moved out of a user note is `llm`, and the parent may become `user` again.

## When Claude writes into a note

If this run adds wording to a `user` note (an `insert_top` summary, say), set `origin: mixed`. Adding frontmatter alone doesn't change origin.

## Example

The uploaded planning doc:
- Lines 1–14 are the user's goals: "snd", "face", "based." mid-sentence. That's **user**.
- Lines 15–193 are a structured draft with PURPOSE/TRIGGER/RULES, ending with "I can build these files… Say go." That's **llm**.

So the note is `mixed`. After the litellm part is split out, that new note is `llm` and the parent stays `mixed`, since its draft rules are still LLM-written.
