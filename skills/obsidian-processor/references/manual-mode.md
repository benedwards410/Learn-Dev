# Manual mode (no Python on the vault's machine)

Use this only when `python3` (or `python`) isn't available where the vault lives. Same decisions, same plan, done with file tools. It's slower and has no automatic undo, so tell the user that and offer to install Python (python.org, or `winget install Python.Python.3.12` on Windows) instead.

1. **Back up first.** Copy every file you'll touch into `VAULT/.obsidian-processor/backups/<YYYYMMDD-HHMMSS>/`, keeping relative paths.
2. **Plan** exactly as in SKILL.md (titles, folders, frontmatter, splits, questions). Write it to `.obsidian-processor/plans/`.
3. **Splits.** For each range, copy the exact lines into the destination:
   - append: at the end, under `> [!info] Moved here from [[Parent]] — date`
   - new note: the lines verbatim
   
   Re-read the destination to confirm the text matches. Only then replace the lines in the parent with `> [!note] Moved to [[Dest]] — date`.
4. **Frontmatter.** Add missing keys only. Never change values the user set. Follow `frontmatter.md`.
5. **Links before moves.** For every renamed note, search the vault for `[[Old Name` and `](Old%20Name` and replace each with the new name. Keep `#heading`, `|alias` and the `!` embed prefix. Skip code blocks.
6. **Move/rename** with `move_file`, one note at a time.
7. **Log.** Append the run section and questions to `99-Meta/Processing Log.md` in the format in `log-and-dashboard.md`. Note that undo is manual: originals are in the backup folder.
