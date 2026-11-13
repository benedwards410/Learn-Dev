# Install obsidian-processor

**Before you start:** an Obsidian vault on this computer · Python 3.9+ (`python3 --version`) · Claude Code or Claude Desktop.

## Claude Code (recommended)

1. Get the skill:
   ```bash
   git clone -b claude/dreamy-faraday-217g4e https://github.com/benedwards410/Learn-Dev
   ```
2. Copy it into your personal skills folder:
   ```bash
   cp -r Learn-Dev/skills/obsidian-processor ~/.claude/skills/
   ```
3. Open Claude Code inside your vault:
   ```bash
   cd ~/path/to/YourVault && claude
   ```
4. Say **"triage my vault"**. Claude asks once which folders to use, then runs.

## Claude Desktop

1. Download `dist/obsidian-processor.skill` from the same branch.
2. In Claude, open **Settings → Capabilities → Skills** and upload the file. Menu names can shift between app versions; look for "Skills".
3. Install the **Desktop Commander** extension and allow your vault folder. This is what lets Claude read and move your notes.
4. Start a chat: **"triage my vault at ~/Documents/YourVault"**. On first use, Claude copies its helper script into the vault's hidden `.obsidian-processor/bin/`.

## Check it worked

```
YourVault/
├── 00-Inbox/
├── 10-Projects/
├── 20-Areas/
├── 30-Reference/
├── 90-Archive/
├── 99-Meta/
│   ├── Processing Log.md     ← every change + undo
│   └── Vault Dashboard.md    ← live tables
└── .obsidian-processor/      ← hidden: config, backups, history
```

## Optional

- **Dataview** plugin: turns *Vault Dashboard* into live tables.
- **Update time on edit** plugin: set to keys `created` and `modified` so dates stay current between runs.
- **Big vault?** Copy it or commit it to git before the first triage. Undo covers every run, and a backup of your own costs nothing.
- **No Python?** Install it from python.org, or `winget install Python.Python.3.12` on Windows. Without it Claude edits files by hand, which is slower and has no automatic undo.
