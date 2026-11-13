# obsidian-processor FAQ

## Safety

**Will it change my writing?** No. Text moves as exact lines, checked byte for byte. It only adds the properties header. Wording changes happen only when you ask, like "add a summary".

**Does it delete anything?** Never. Older duplicates and dead notes move to `90-Archive`.

**Will renaming break my links?** No. It rewrites every `[[link]]`, `![[embed]]`, heading link, aliased link and relative markdown link across the vault. Links inside code are left alone.

**How do I undo?** Say "undo the last obsidian-processor run". Originals come back from a backup, byte for byte. If you edited a note since the run, it stops and asks first.

**Does my vault leave my computer?** Claude reads the notes it processes, as in any chat. The helper script runs on your machine and makes no network calls.

**Can I keep Obsidian open?** Yes. It reloads changed files. Just don't edit a note while a run is applying.

## How it decides

**What if it isn't sure?** It doesn't guess. The note stays in `00-Inbox` as a draft, and a question lands under **Needs you** in the log.

**When does it split a note?** Only when a section is a different topic, is 8+ lines or 15%+ of the note, and is something you'd never look for there. It goes to the matching note, or a new one, with a link left behind.

**What does "origin" mean?** `user`, `llm`, `mixed` or `unknown`. Chat markers and "Say go."-style closers point to an LLM. Typos and shorthand point to you. It's unknown when there's too little to tell.

**Where do the dates come from?** `created`: your existing value, otherwise the earliest file date or a date in the filename. `modified`: your last real edit, not the day it added properties.

**I already have my own folders.** On the first run it maps onto them (your Inbox, your Archive) instead of making parallel ones. You confirm once.

**What does it never touch?** Daily notes get properties only and are never moved. It never touches templates, `.obsidian`, images, PDFs, or notes marked `processor: skip`.

**My vault has 1,000 notes.** It works in batches of 25 and reports each one. Later runs pick up only new or edited notes, so they're quick.

**Why does my note still start with the old heading?** Headings are your words, so they stay. Say "update the headings to match the titles" if you want them changed.
