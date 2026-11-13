# obsidian-processor

A Claude skill that keeps an Obsidian vault organized. Say **"triage my vault"**, and it reads your notes and then:

| | What it does |
|---|---|
| 📁 | **Files** each note into `00-Inbox` · `10-Projects` · `20-Areas` · `30-Reference` · `90-Archive` |
| 🏷️ | **Names** notes from their content ("kce notes final v2" → "KCE Ops Notes") and fixes every `[[link]]` to them |
| 🧾 | **Adds frontmatter**: description, category, tags, status, origin (user / llm / mixed), created and modified dates, related notes |
| ✂️ | **Splits** notes that mix topics (fantasy football inside a work note moves out, word for word, with a link left behind) |
| 🗄️ | **Archives** the older copy of a duplicate. Nothing is ever deleted |
| 📜 | **Logs** every change in `99-Meta/Processing Log.md`, with one-step **undo** |

One-pagers: [Install](docs/INSTALL.md) · [Use](docs/USAGE.md) · [FAQ](docs/FAQ.md)

## Install

**Claude Code** (works on the vault directly):
```bash
cp -r skills/obsidian-processor ~/.claude/skills/
```

**Claude Desktop**: upload `dist/obsidian-processor.skill` under Skills in Claude's settings. Claude also needs file access to the vault, through the **Desktop Commander** extension. On first use, Claude copies the helper script into `<vault>/.obsidian-processor/bin/`.

Needs Python 3.9+ on the machine with the vault. There's a slower manual fallback without it.

## Use

| Say | What happens |
|---|---|
| "triage my vault" | processes every note that's new, edited, or loose in the root/Inbox, in batches of 25 |
| "file my inbox" | just `00-Inbox` and the vault root |
| "process *Note Name*" | one note |
| "process *Note*: add a plain-English summary at the top" | adds the summary, leaves the rest untouched |
| "undo the last obsidian-processor run" | puts every file back exactly as it was |

**First run only:** Claude shows the folder map it will use and asks once. After that, runs are automatic.

Each run ends with a bottom line, a table (file · new title · category · status · origin · folder · action · reason), any questions it wouldn't guess, and the undo command.

## In Obsidian

- **Ctrl/Cmd + O → "Processing Log"** shows the full history and the **Needs you** checklist.
- **Ctrl/Cmd + O → "Vault Dashboard"** shows live tables by status, category and origin. It needs the [Dataview](https://github.com/blacksmithgu/obsidian-dataview) plugin.
- Optional: the **Update time on edit** plugin, set to the keys `created` and `modified`, keeps dates current between runs.
- Put `processor: skip` in a note's properties to have the skill leave it alone.

## How it's built

```
skills/obsidian-processor/
├── SKILL.md                  workflow Claude follows
├── references/               frontmatter, filing, splitting, origin, log, manual mode
├── scripts/vault.py          scan · outline · related · apply · undo · check (stdlib only)
└── assets/                   plan schema + example
tests/                        fixture vault + unittest suite
dist/obsidian-processor.skill packaged skill for upload
```

Claude makes the judgment calls (what a note is about, where it goes). `vault.py` does the risky file work: exact line cuts, link rewrites, backups and undo. Your text is never retyped by a model.

```bash
python3 -m unittest discover -s tests -v      # 40 tests
python3 skills/obsidian-processor/scripts/vault.py --help
```
