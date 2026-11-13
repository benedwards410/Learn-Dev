#!/usr/bin/env python3
"""obsidian-processor vault tool.

The obsidian-processor skill uses this for the deterministic, reversible file
work. Claude decides what each note is and where it belongs, then writes a
PLAN.json. This script makes the cuts, renames, moves, link fixes, log entries
and backups, so note content is never retyped by a model.

Python 3.9+, standard library only.

  vault.py init    VAULT [--config-json JSON]
  vault.py scan    VAULT [--scope changed|inbox|all] [--paths P ...] [--out FILE]
  vault.py outline VAULT NOTE [--json]
  vault.py related VAULT NOTE [NOTE ...] [--top N] [--plan PLAN]
  vault.py apply   VAULT PLAN [--dry-run] [--now ISO]
  vault.py undo    VAULT [--run ID] [--force]
  vault.py check   VAULT [--json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import posixpath
import re
import sys
import tempfile
import urllib.parse
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

VERSION = "1.0.0"
STATE_DIR = ".obsidian-processor"
LOG_NAME = "Processing Log"
DASHBOARD_NAME = "Vault Dashboard"
RUNS_MARKER = "<!-- obsidian-processor: runs below, newest first -->"
NEEDS_HEADING = "## Needs you"

DEFAULT_CONFIG = {
    "version": 1,
    "folders": {
        "inbox": "00-Inbox",
        "projects": "10-Projects",
        "areas": "20-Areas",
        "reference": "30-Reference",
        "archive": "90-Archive",
        "meta": "99-Meta",
    },
    "categories": [],
    "exclude": ["Templates", "templates"],
    "split_min_lines": 8,
    "split_min_share": 0.15,
    "code_only_threshold": 0.8,
    "related_count": 5,
    "subfolder_min_notes": 3,
    "batch_size": 25,
}

# Frontmatter keys, in the order new keys are written.
KEY_ORDER = [
    "title", "description", "category", "tags", "status", "origin",
    "created", "modified", "related", "aliases", "supersedes",
    "superseded_by", "split_from", "processed",
]
MANAGED_KEYS = {"modified", "processed", "superseded_by"}   # skill may overwrite
UNION_KEYS = {"tags", "aliases", "related"}                  # skill only adds items
LINK_KEYS = {"related", "supersedes", "superseded_by", "split_from"}
LIFECYCLE_STATUS = {"superseded", "archived"}               # may overwrite status
CREATED_SYNONYMS = ["created", "date created", "created_at", "creation date", "date"]
VALID_STATUS = {"draft", "active", "superseded", "archived"}
VALID_ORIGIN = {"user", "llm", "mixed", "unknown"}

BAD_NAME_CHARS = set('#|^:%[]/\\*"<>?')
VERSION_WORD_RE = re.compile(r"(\bv\d+(\.\d+)*\b|\bfinal\b|\bcopy\b|\(\d+\)\s*$)", re.I)
SOFT_VERSION_RE = re.compile(r"\b(new|old|latest|updated|revised)\b", re.I)
DAILY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
JUNK_NAME_RE = re.compile(r"^(untitled( \d+)?|new note( \d+)?)$", re.I)
DATE_IN_NAME_RE = re.compile(r"(20\d{2}|19\d{2})-(\d{2})-(\d{2})")

KEY_RE = re.compile(r"^([^\s#\-][^:]*):(?:[ \t]+(.*))?$")
WIKILINK_RE = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
MDLINK_RE = re.compile(r"(!?\[[^\]\n]*\]\()(<[^>\n]+>|[^)\s]+)((?:\s+\"[^\"\n]*\")?\))")
INLINE_TAG_RE = re.compile(r"(?<![\w/&#\[])#([A-Za-z0-9_\-/]*[A-Za-z_\-/][A-Za-z0-9_\-/]*)")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
CHAT_RE = re.compile(
    r"^\s*(\*\*)?(you said|chatgpt said|claude said|user|assistant|human|ai|me|prompt|response)(\*\*)?\s*:",
    re.I,
)
TOKEN_RE = re.compile(r"[a-z][a-z0-9_'\-]{2,}")
STOPWORDS = set("""
a about above after again against all also am an and any are aren as at be because been before being below
between both but by can cannot could did do does doing done don down during each else etc even every few for
from further get gets got had has have having he her here hers him his how however i if in into is isn it its
itself just keep like make makes many may me more most much must my no nor not now of off on once one only or
other our ours out over own per put same she should so some such than that the their them then there these
they this those through to too under until up upon use used uses using very via was way we were what when
where which while who whom why will with within without would yes yet you your yours
http https www com org net md png jpg pdf true false null none
""".split())


# ---------------------------------------------------------------- basics

class PlanError(Exception):
    pass


def now_local(override: str | None = None) -> dt.datetime:
    value = override or os.environ.get("OBSIDIAN_PROCESSOR_NOW")
    if value:
        return dt.datetime.fromisoformat(value).replace(microsecond=0)
    return dt.datetime.now().replace(microsecond=0)


def emit(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_note(path: Path) -> tuple[str, dict]:
    """Read a note as text with '\n' newlines; remember BOM and newline style."""
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    if bom:
        raw = raw[3:]
    text = raw.decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), {"bom": bom, "nl": nl}


def encode_note(text: str, fmt: dict) -> bytes:
    if fmt.get("nl") == "\r\n":
        text = text.replace("\n", "\r\n")
    data = text.encode("utf-8")
    return b"\xef\xbb\xbf" + data if fmt.get("bom") else data


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".op-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def stem(rel: str) -> str:
    name = posixpath.basename(rel)
    return name[:-3] if name.lower().endswith(".md") else name


def parent_dir(rel: str) -> str:
    return posixpath.dirname(rel)


def join_rel(folder: str, name: str) -> str:
    folder = (folder or "").strip("/")
    return f"{folder}/{name}" if folder else name


# ---------------------------------------------------------------- config / vault walk

def state_dir(vault: Path) -> Path:
    return vault / STATE_DIR


def load_config(vault: Path) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    path = state_dir(vault) / "config.json"
    if path.exists():
        user = json.loads(path.read_text(encoding="utf-8"))
        deep_merge(cfg, user)
        cfg["_initialized"] = True
    else:
        cfg["_initialized"] = False
    # Obsidian's own settings: template folder is never processed, daily-notes folder is special.
    templates = read_obsidian_setting(vault, "templates.json", "folder")
    if templates:
        cfg["exclude"] = list(dict.fromkeys(cfg["exclude"] + [templates.strip("/")]))
    cfg["_daily_folder"] = (read_obsidian_setting(vault, "daily-notes.json", "folder") or "").strip("/")
    return cfg


def read_obsidian_setting(vault: Path, filename: str, key: str):
    path = vault / ".obsidian" / filename
    try:
        return json.loads(path.read_text(encoding="utf-8")).get(key)
    except Exception:
        return None


def deep_merge(base: dict, extra: dict) -> dict:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def save_config(vault: Path, cfg: dict) -> None:
    clean = {k: v for k, v in cfg.items() if not k.startswith("_")}
    atomic_write(state_dir(vault) / "config.json",
                 (json.dumps(clean, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def walk_files(vault: Path):
    """Every file in the vault outside dot-folders (.obsidian, .trash, .git, state dir)."""
    for root, dirs, files in os.walk(vault):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if name.startswith("."):
                continue
            full = Path(root) / name
            yield full.relative_to(vault).as_posix()


def all_md(vault: Path) -> list[str]:
    return [p for p in walk_files(vault) if p.lower().endswith(".md")]


def meta_folder(cfg: dict) -> str:
    return cfg["folders"]["meta"].strip("/")


def is_processable(rel: str, cfg: dict) -> bool:
    """Notes the skill may file/edit (excludes meta folder and excluded folders)."""
    parts = rel.split("/")
    excluded = {e.strip("/").lower() for e in cfg.get("exclude", [])}
    if parts[0].lower() == meta_folder(cfg).lower():
        return False
    for i in range(1, len(parts)):
        if "/".join(parts[:i]).lower() in excluded or parts[i - 1].lower() in excluded:
            return False
    return True


def is_daily(rel: str, cfg: dict) -> bool:
    if DAILY_RE.match(stem(rel)):
        return True
    folder = cfg.get("_daily_folder")
    return bool(folder) and rel.lower().startswith(folder.lower() + "/")


# ---------------------------------------------------------------- frontmatter

def looks_like_yaml(block: list[str]) -> bool:
    """Guard against a note that merely starts with a horizontal rule."""
    keyed = False
    for line in block:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1].isspace() or line.startswith("- "):
            if not keyed:
                return False
            continue
        if not KEY_RE.match(line):
            return False
        keyed = True
    return True


def split_frontmatter(text: str):
    """Return (fm_lines | None, body, fm_line_count). fm_line_count counts both fences."""
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return None, text, 0
    for i in range(1, len(lines)):
        if lines[i].rstrip() in ("---", "..."):
            if not looks_like_yaml(lines[1:i]):
                return None, text, 0
            return lines[1:i], "\n".join(lines[i + 1:]), i + 1
    return None, text, 0


def parse_entries(fm_lines: list[str]) -> list[list]:
    entries: list[list] = []
    for line in fm_lines:
        match = KEY_RE.match(line)
        if match and not line[:1].isspace():
            entries.append([match.group(1).strip(), [line]])
        elif entries:
            entries[-1][1].append(line)
        else:
            entries.append([None, [line]])
    return entries


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return json.loads(value)
        except Exception:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def split_flow(inner: str) -> list[str]:
    items, buf, depth, quote = [], [], 0, None
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        elif ch == "," and depth == 0:
            items.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if "".join(buf).strip():
        items.append("".join(buf))
    return items


def strip_comment(value: str) -> str:
    quote = None
    for i, ch in enumerate(value):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and i > 0 and value[i - 1] in " \t":
            return value[:i].rstrip()
    return value


def parse_value(raw_lines: list[str]):
    match = KEY_RE.match(raw_lines[0])
    inline = (match.group(2) or "").strip() if match else ""
    rest = raw_lines[1:]
    if inline in ("", "|", ">", "|-", ">-", "|+", ">+"):
        items = []
        for line in rest:
            s = line.strip()
            if s.startswith("- "):
                items.append(unquote(s[2:]))
            elif s == "-":
                items.append("")
        if items:
            return items
        if inline:
            return "\n".join(line.strip() for line in rest)
        return None
    inline = strip_comment(inline)
    if inline.startswith("[") and inline.endswith("]") and not inline.startswith("[["):
        return [unquote(x) for x in split_flow(inline[1:-1]) if x.strip()]
    return unquote(inline)


def frontmatter_dict(fm_lines) -> dict:
    out = {}
    for key, raw in parse_entries(fm_lines or []):
        if key:
            out[key] = parse_value(raw)
    return out


def yaml_scalar(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    if s == "":
        return '""'
    needs_quotes = (
        s[0] in "[]{}&*!|>'\"%@`#,?:-" or s != s.strip() or ": " in s or " #" in s
        or s.endswith(":") or "\n" in s or "[[" in s
        or s.lower() in {"true", "false", "yes", "no", "null", "~", "on", "off"}
        or re.fullmatch(r"[-+]?\d+(\.\d+)?", s) is not None
    )
    return json.dumps(s, ensure_ascii=False) if needs_quotes else s


def yaml_entry(key: str, value) -> list[str]:
    if isinstance(value, (list, tuple)):
        if not value:
            return [f"{key}: []"]
        return [f"{key}:"] + [f"  - {yaml_scalar(v)}" for v in value]
    return [f"{key}: {yaml_scalar(value)}".rstrip()]


def as_list(value) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [v for v in value if v not in (None, "")]
    return [v for v in re.split(r"[,\s]+", str(value)) if v]


def norm_item(key: str, value) -> str:
    s = str(value).strip()
    if key == "tags":
        return s.lstrip("#").lower()
    if key == "related":
        return link_name(s).lower()
    return s.lower()


def link_name(value: str) -> str:
    """'[[Name|x]]' -> 'Name';  'Name' -> 'Name'."""
    s = str(value).strip()
    match = re.fullmatch(r"!?\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\\?\|[^\]]*)?\]\]", s)
    if match:
        s = match.group(1)
    if s.lower().endswith(".md"):
        s = s[:-3]
    return posixpath.basename(s.strip())


def merge_frontmatter(fm_lines, updates: dict, force: set | None = None) -> list[str]:
    """Merge updates into existing frontmatter lines without disturbing user fields.

    - absent key      -> added (canonical order, at the end)
    - UNION_KEYS      -> new items appended, existing items untouched
    - MANAGED_KEYS    -> overwritten
    - status          -> overwritten only for lifecycle moves (superseded/archived)
    - keys in `force` -> overwritten (caller decided the old value was the skill's own)
    - anything else   -> the user's value wins
    """
    force = {k.lower() for k in (force or set())}
    entries = parse_entries(fm_lines or [])
    index = {e[0].lower(): e for e in entries if e[0]}
    ordered = sorted(updates, key=lambda k: KEY_ORDER.index(k) if k in KEY_ORDER else len(KEY_ORDER))
    for key in ordered:
        value = updates[key]
        if value is None:
            continue
        entry = index.get(key.lower())
        if entry is None:
            if isinstance(value, list) and not value and key != "tags":
                continue
            entry = [key, yaml_entry(key, value)]
            entries.append(entry)
            index[key.lower()] = entry
            continue
        current = parse_value(entry[1])
        if key in UNION_KEYS:
            existing = as_list(current)
            seen = {norm_item(key, v) for v in existing}
            additions = [v for v in as_list(value) if norm_item(key, v) not in seen]
            if additions:
                entry[1] = yaml_entry(entry[0], existing + additions)
        elif key in MANAGED_KEYS or key.lower() in force or (key == "status" and value in LIFECYCLE_STATUS):
            if str(current) != str(value):
                entry[1] = yaml_entry(entry[0], value)
    return [line for e in entries for line in e[1]]


def compose(fm_lines, body: str) -> str:
    if fm_lines is None:
        return body
    return "---\n" + "\n".join(fm_lines) + ("\n" if fm_lines else "") + "---\n" + body


# ---------------------------------------------------------------- markdown structure

def fence_spans(lines: list[str]) -> list[tuple[int, int]]:
    """1-based inclusive (start, end) line spans of fenced code blocks (opening to closing fence)."""
    spans, opener, start = [], None, 0
    for i, line in enumerate(lines):
        match = FENCE_RE.match(line)
        if opener is None:
            if match:
                opener, start = match.group(1), i
        elif match and match.group(1)[0] == opener[0] and len(match.group(1)) >= len(opener) \
                and line.strip() == match.group(1):
            spans.append((start + 1, i + 1))
            opener = None
    if opener is not None:
        spans.append((start + 1, len(lines)))
    return spans


def fence_map(lines: list[str]) -> list[bool]:
    """in_code[i] is True when line i (0-based) is part of a fenced code block."""
    flags = [False] * len(lines)
    for start, end in fence_spans(lines):
        for i in range(start - 1, end):
            flags[i] = True
    return flags


def code_regions(text: str) -> list[tuple[int, int]]:
    """Character ranges covered by fenced code or inline code."""
    regions, offset = [], 0
    lines = text.split("\n")
    flags = fence_map(lines)
    for line, in_code in zip(lines, flags):
        if in_code:
            regions.append((offset, offset + len(line)))
        else:
            for match in re.finditer(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)", line):
                regions.append((offset + match.start(), offset + match.end()))
        offset += len(line) + 1
    return regions


def in_regions(pos: int, regions) -> bool:
    return any(a <= pos < b for a, b in regions)


def outline_blocks(text: str) -> dict:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    fm_lines, _, fm_count = split_frontmatter(text)
    flags = fence_map(lines)
    span_end = {s - 1: e - 1 for s, e in fence_spans(lines)}
    blocks, i = [], fm_count
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        start = i
        if i in span_end:
            i = span_end[i]
            kind = "code"
        elif HEADING_RE.match(line):
            kind = "heading"
        elif re.match(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$", line):
            kind = "rule"
        else:
            while i + 1 < len(lines) and lines[i + 1].strip() and not flags[i + 1] \
                    and not HEADING_RE.match(lines[i + 1]) and not CHAT_RE.match(lines[i + 1]):
                i += 1
            first = lines[start].lstrip()
            if CHAT_RE.match(lines[start]):
                kind = "chat"
            elif first.startswith(("- ", "* ", "+ ")) or re.match(r"^\d+[.)]\s", first):
                kind = "list"
            elif first.startswith("|"):
                kind = "table"
            elif first.startswith(">"):
                kind = "quote"
            else:
                kind = "para"
        blocks.append({
            "start": start + 1, "end": i + 1, "kind": kind,
            "preview": re.sub(r"\s+", " ", " ".join(lines[start:i + 1]))[:90],
        })
        i += 1
    sections = []
    heads = [(b["start"], len(HEADING_RE.match(lines[b["start"] - 1]).group(1)),
              HEADING_RE.match(lines[b["start"] - 1]).group(2))
             for b in blocks if b["kind"] == "heading"]
    for idx, (line_no, level, title) in enumerate(heads):
        end = len(lines)
        for nxt_line, nxt_level, _ in heads[idx + 1:]:
            if nxt_level <= level:
                end = nxt_line - 1
                break
        while end > line_no and not lines[end - 1].strip():
            end -= 1
        sections.append({"start": line_no, "end": end, "level": level, "heading": title})
    return {"lines": len(lines), "frontmatter_lines": fm_count, "blocks": blocks, "sections": sections}


def code_ratio(body: str) -> float:
    lines = body.split("\n")
    flags = fence_map(lines)
    nonblank = [(l, f) for l, f in zip(lines, flags) if l.strip()]
    if not nonblank:
        return 0.0
    codeish = sum(1 for l, f in nonblank if f or l.lstrip().startswith("|"))
    return round(codeish / len(nonblank), 2)


def strip_code(body: str) -> str:
    lines = body.split("\n")
    return "\n".join(l for l, f in zip(lines, fence_map(lines)) if not f)


def inline_tags(body: str) -> list[str]:
    text = strip_code(body)
    text = re.sub(r"`[^`\n]*`", " ", text)
    tags = []
    for line in text.split("\n"):
        if HEADING_RE.match(line) and line.startswith("#"):
            line = HEADING_RE.match(line).group(2)
        tags += [m.group(1).lower() for m in INLINE_TAG_RE.finditer(line)]
    return list(dict.fromkeys(tags))


# ---------------------------------------------------------------- dates

def to_date(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if match:
        return match.group(0)
    for fmt in ("%m/%d/%Y", "%d %B %Y", "%B %d, %Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def created_guess(path: Path, rel: str, fm: dict) -> str:
    lowered = {k.lower(): v for k, v in fm.items()}
    for key in CREATED_SYNONYMS:
        if key in lowered and to_date(lowered[key]):
            return to_date(lowered[key])
    st = path.stat()
    stamps = [st.st_mtime, st.st_ctime]
    if getattr(st, "st_birthtime", None):
        stamps.append(st.st_birthtime)
    dates = [dt.date.fromtimestamp(t).isoformat() for t in stamps if t > 631152000]  # after 1990
    match = DATE_IN_NAME_RE.search(posixpath.basename(rel))
    if match:
        dates.append(match.group(0))
    return min(dates) if dates else dt.date.today().isoformat()


def mtime_dt(path: Path) -> dt.datetime:
    return dt.datetime.fromtimestamp(path.stat().st_mtime).replace(microsecond=0)


def processed_dt(fm: dict):
    value = fm.get("processed")
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None


def edited_since_processed(path: Path, fm: dict) -> bool:
    processed = processed_dt(fm)
    if processed is None:
        return True
    return mtime_dt(path) > processed + dt.timedelta(seconds=120)


# ---------------------------------------------------------------- link resolution

class Resolver:
    """Resolve wikilinks and markdown links the way Obsidian does (closely enough)."""

    def __init__(self, files: list[str]):
        self.files = set(files)
        self.lower = {f.lower(): f for f in files}
        self.by_name: dict[str, list[str]] = defaultdict(list)
        for f in files:
            name = posixpath.basename(f)
            self.by_name[name.lower()].append(f)
            if name.lower().endswith(".md"):
                self.by_name[name[:-3].lower()].append(f)

    def _exact(self, rel: str):
        rel = posixpath.normpath(rel).lstrip("/")
        if rel.startswith(".."):
            return None
        for cand in (rel, rel + ".md"):
            if cand.lower() in self.lower:
                return self.lower[cand.lower()]
        return None

    def wikilink(self, target: str, source: str):
        t = target.strip()
        if not t:
            return None
        if "/" in t:
            hit = self._exact(t) or self._exact(posixpath.join(parent_dir(source), t))
            if hit:
                return hit
            suffix = "/" + t.lower()
            ends = [f for f in self.files if f.lower().endswith(suffix) or f.lower().endswith(suffix + ".md")]
            return ends[0] if len(ends) == 1 else None
        cands = self.by_name.get(t.lower(), [])
        if not cands:
            return None
        if len(cands) == 1:
            return cands[0]
        same = [c for c in cands if parent_dir(c) == parent_dir(source)]
        return same[0] if same else sorted(cands, key=lambda c: (c.count("/"), len(c)))[0]

    def mdlink(self, target: str, source: str):
        return self._exact(posixpath.join(parent_dir(source), target)) or self._exact(target)


def split_wikilink(inner: str):
    match = re.match(r"^(.*?)(\\\||\|)(.*)$", inner, re.S)
    if match:
        link, sep, display = match.group(1), match.group(2), match.group(3)
    else:
        link, sep, display = inner, "", ""
    if "#" in link:
        target, sub = link.split("#", 1)
        sub = "#" + sub
    else:
        target, sub = link, ""
    return target, sub, sep, display


def new_link_target(target: str, old_rel: str, new_rel: str, src_new: str) -> str:
    """Compute the replacement target text for a link that pointed at old_rel."""
    had_md = target.lower().endswith(".md")
    if "/" not in target:
        out = posixpath.basename(new_rel)
    elif target.startswith(("./", "../")):
        out = posixpath.relpath(new_rel, parent_dir(src_new) or ".")
    else:
        out = new_rel
    if not had_md and out.lower().endswith(".md"):
        out = out[:-3]
    return out


def rewrite_links(text: str, src_old: str, src_new: str, moves: dict, resolver: Resolver) -> tuple[str, int]:
    """Rewrite wikilinks + markdown links that point at moved notes. Code is left alone."""
    regions = code_regions(text)
    count = 0

    def wiki(match):
        nonlocal count
        if in_regions(match.start(), regions):
            return match.group(0)
        bang, inner = match.group(1), match.group(2)
        target, sub, sep, display = split_wikilink(inner)
        hit = resolver.wikilink(target, src_old)
        if not hit:
            return match.group(0)
        relative_path_link = "/" in target and target.strip().startswith(("./", "../"))
        if hit not in moves and not (relative_path_link and src_old != src_new):
            return match.group(0)
        new_rel = moves.get(hit, hit)
        new_target = new_link_target(target.strip(), hit, new_rel, src_new)
        if new_target == target.strip():
            return match.group(0)
        count += 1
        return f"{bang}[[{new_target}{sub}{sep}{display}]]"

    def md(match):
        nonlocal count
        if in_regions(match.start(), regions):
            return match.group(0)
        head, raw, tail = match.group(1), match.group(2), match.group(3)
        angled = raw.startswith("<")
        target = raw[1:-1] if angled else raw
        if re.match(r"^[a-z][a-z0-9+.\-]*:", target, re.I) or target.startswith("#"):
            return match.group(0)
        path_part, _, frag = target.partition("#")
        decoded = urllib.parse.unquote(path_part)
        rel_hit = resolver._exact(posixpath.join(parent_dir(src_old), decoded))
        root_hit = None if rel_hit else resolver._exact(decoded)
        hit = rel_hit or root_hit
        if not hit or (hit not in moves and not (rel_hit and src_old != src_new)):
            return match.group(0)
        new_rel = moves.get(hit, hit)
        if rel_hit:
            out = posixpath.relpath(new_rel, parent_dir(src_new) or ".")
        else:
            out = new_rel
        if not decoded.lower().endswith(".md") and out.lower().endswith(".md"):
            out = out[:-3]
        if not angled and ("%20" in path_part or " " in out):
            out = urllib.parse.quote(out, safe="/()-_.~")
        new_raw = out + (("#" + frag) if frag else "")
        if angled:
            new_raw = f"<{new_raw}>"
        if new_raw == raw:
            return match.group(0)
        count += 1
        return f"{head}{new_raw}{tail}"

    text = WIKILINK_RE.sub(wiki, text)
    regions = code_regions(text)
    text = MDLINK_RE.sub(md, text)
    return text, count


# ---------------------------------------------------------------- validation helpers

def title_problems(title: str) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    if not title or not title.strip():
        return ["empty title"], warnings
    bad = sorted(set(title) & BAD_NAME_CHARS)
    if bad:
        errors.append(f"title {title!r} has characters Obsidian links can't use: {' '.join(bad)}")
    if title != title.strip() or title.endswith("."):
        errors.append(f"title {title!r} has leading/trailing spaces or a trailing dot")
    if VERSION_WORD_RE.search(title):
        errors.append(f"title {title!r} contains a version word (v2/final/copy/(1)); one living note per topic")
    elif SOFT_VERSION_RE.search(title):
        warnings.append(f"title {title!r} contains new/old/latest/updated; is that part of the topic?")
    if len(title) > 120:
        errors.append(f"title {title[:40]!r}... is longer than 120 characters")
    return errors, warnings


def folder_problems(folder: str) -> list[str]:
    if folder in ("", None):
        return []
    if folder.startswith("/") or re.match(r"^[A-Za-z]:", folder):
        return [f"folder {folder!r} must be relative to the vault"]
    parts = folder.strip("/").split("/")
    if any(p in ("", ".", "..") or p.startswith(".") for p in parts):
        return [f"folder {folder!r} may not contain '.', '..' or dot-folders"]
    if any(set(p) & (BAD_NAME_CHARS - {"/"}) for p in parts):
        return [f"folder {folder!r} contains characters that are unsafe in paths"]
    return []


# ---------------------------------------------------------------- init

LOG_TEMPLATE = """---
title: Processing Log
description: Every change obsidian-processor made to this vault, newest run first.
category: Meta
tags:
  - meta
  - obsidian-processor
status: active
origin: llm
created: {today}
---
# Processing Log

> [!info] How to use this log
> - Every **obsidian-processor** run adds a section below (newest first): what was created, renamed, moved, split, appended or superseded, and why.
> - Open it any time with **Ctrl/Cmd + O → "Processing Log"**, or bookmark it. [[Vault Dashboard]] has live views by status, category and origin.
> - **Needs you** lists questions the skill would not guess. Tick the box when you've answered (or just tell Claude the answer).
> - To reverse a run, tell Claude **"undo obsidian-processor run <run id>"** or **"undo the last obsidian-processor run"**.

{needs}
{marker}
"""

DASHBOARD_TEMPLATE = """---
title: Vault Dashboard
description: Live views of the vault by status, category, origin and recent processing. Needs the Dataview plugin.
category: Meta
tags:
  - meta
  - obsidian-processor
status: active
origin: llm
created: {today}
---
# Vault Dashboard

> [!tip] These tables need the **Dataview** community plugin (Settings → Community plugins → Browse → "Dataview"). Without it you'll see the raw queries. Change history lives in [[Processing Log]].

## Recently processed
```dataview
TABLE category, status, origin, processed
FROM -"{meta}"
WHERE processed
SORT processed DESC
LIMIT 25
```

## Waiting in the Inbox
```dataview
TABLE description, created
FROM "{inbox}"
SORT created DESC
```

## By category
```dataview
TABLE WITHOUT ID category AS Category, length(rows) AS Notes, rows.file.link AS Files
FROM -"{meta}" AND -"{archive}"
WHERE category
GROUP BY category
SORT category ASC
```

## Written by an LLM (or partly)
```dataview
TABLE origin, category, created
FROM -"{meta}"
WHERE origin = "llm" OR origin = "mixed"
SORT created DESC
```

## Split out of other notes
```dataview
TABLE split_from, created
FROM -"{meta}"
WHERE split_from
SORT created DESC
```

## Superseded
```dataview
TABLE superseded_by, modified
FROM -"{meta}"
WHERE status = "superseded"
SORT modified DESC
```
"""


def log_path(vault: Path, cfg: dict) -> Path:
    return vault / meta_folder(cfg) / f"{LOG_NAME}.md"


def cmd_init(vault: Path, config_json: str | None) -> int:
    cfg = load_config(vault)
    if config_json:
        deep_merge(cfg, json.loads(config_json))
    created = []
    for sub in ("runs", "backups", "plans"):
        (state_dir(vault) / sub).mkdir(parents=True, exist_ok=True)
    if not (state_dir(vault) / "config.json").exists() or config_json:
        save_config(vault, cfg)
        created.append(f"{STATE_DIR}/config.json")
    for folder in cfg["folders"].values():
        path = vault / folder
        if not path.exists():
            path.mkdir(parents=True)
            created.append(folder + "/")
    today = now_local().date().isoformat()
    lp = log_path(vault, cfg)
    if not lp.exists():
        atomic_write(lp, LOG_TEMPLATE.format(today=today, needs=NEEDS_HEADING + "\n", marker=RUNS_MARKER).encode())
        created.append(lp.relative_to(vault).as_posix())
    dp = vault / meta_folder(cfg) / f"{DASHBOARD_NAME}.md"
    if not dp.exists():
        f = cfg["folders"]
        atomic_write(dp, DASHBOARD_TEMPLATE.format(
            today=today, meta=f["meta"], inbox=f["inbox"], archive=f["archive"]).encode())
        created.append(dp.relative_to(vault).as_posix())
    emit({"ok": True, "version": VERSION, "vault": str(vault), "created": created,
          "config": {k: v for k, v in load_config(vault).items() if not k.startswith("_")}})
    return 0


# ---------------------------------------------------------------- scan

def note_info(vault: Path, rel: str, cfg: dict, detail: bool = True) -> dict:
    path = vault / rel
    text, _ = read_note(path)
    fm_lines, body, fm_count = split_frontmatter(text)
    fm = frontmatter_dict(fm_lines)
    tags = list(dict.fromkeys([norm_item("tags", t) for t in as_list(fm.get("tags"))] + inline_tags(body)))
    ratio = code_ratio(body)
    lines = text.split("\n")
    flags = fence_map(lines)
    headings = [{"line": i + 1, "level": len(m.group(1)), "text": m.group(2)}
                for i, (line, f) in enumerate(zip(lines, flags))
                if i >= fm_count and not f and (m := HEADING_RE.match(line))]
    folder = parent_dir(rel)
    info = {
        "path": rel,
        "name": stem(rel),
        "folder": folder,
        "top_folder": rel.split("/")[0] if "/" in rel else "",
        "has_frontmatter": fm_lines is not None,
        "frontmatter": fm,
        "category": fm.get("category"),
        "status": fm.get("status"),
        "tags": tags,
        "lines": len(lines) - (1 if lines and lines[-1] == "" else 0),
        "words": len(re.findall(r"\S+", strip_code(body))),
        "code_ratio": ratio,
        "mostly_code": ratio > cfg["code_only_threshold"],
        "daily_note": is_daily(rel, cfg),
        "skip": str(fm.get("processor", "")).lower() == "skip",
        "created_guess": created_guess(path, rel, fm),
        "mtime": mtime_dt(path).isoformat(),
        "processed": fm.get("processed"),
        "needs_processing": (fm_lines is None or edited_since_processed(path, fm)
                             or folder.lower() in ("", cfg["folders"]["inbox"].lower())),
    }
    if detail:
        info["headings"] = headings[:40]
        info["links_out"] = sorted({split_wikilink(m.group(2))[0].strip()
                                    for m in WIKILINK_RE.finditer(text) if split_wikilink(m.group(2))[0].strip()})[:60]
        info["preview"] = re.sub(r"\s+", " ", body.strip())[:280]
    return info


def cmd_scan(vault: Path, scope: str, paths: list[str] | None, out: str | None) -> int:
    cfg = load_config(vault)
    notes = [p for p in all_md(vault) if is_processable(p, cfg)]
    folders, categories, tags = Counter(), Counter(), Counter()
    cat_folders: dict[str, Counter] = defaultdict(Counter)
    infos, errors = [], []
    wanted = {p.strip("/") for p in paths} if paths else None
    inbox = cfg["folders"]["inbox"].lower()
    for rel in notes:
        try:
            brief = note_info(vault, rel, cfg, detail=False)
        except UnicodeDecodeError:
            errors.append(f"{rel}: not UTF-8 text, skipped")
            continue
        folders[brief["top_folder"] or "(vault root)"] += 1
        if brief["category"]:
            categories[str(brief["category"])] += 1
            cat_folders[str(brief["category"])][brief["top_folder"] or "(vault root)"] += 1
        for t in brief["tags"]:
            tags[t] += 1
        if wanted is not None:
            take = rel in wanted
        elif scope == "all":
            take = True
        elif scope == "inbox":
            take = brief["folder"].lower() in ("", inbox) or brief["folder"].lower().startswith(inbox + "/")
        else:
            take = brief["needs_processing"] and not brief["skip"]
        if take:
            infos.append(note_info(vault, rel, cfg, detail=True))
    result = {
        "version": VERSION,
        "vault": str(vault),
        "initialized": cfg["_initialized"],
        "now": now_local().isoformat(),
        "config": {k: v for k, v in cfg.items() if not k.startswith("_")},
        "daily_notes_folder": cfg["_daily_folder"] or None,
        "counts": {"notes": len(notes), "in_scope": len(infos)},
        "top_folders": dict(folders.most_common()),
        "categories": dict(categories.most_common()),
        "category_folders": {k: dict(v) for k, v in cat_folders.items()},
        "tags": dict(tags.most_common(150)),
        "all_notes": notes,
        "scope": "paths" if wanted is not None else scope,
        "notes": infos,
        "errors": errors,
    }
    if out:
        Path(out).write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        emit({"ok": True, "out": out, "counts": result["counts"], "initialized": result["initialized"],
              "top_folders": result["top_folders"], "errors": errors})
    else:
        emit(result)
    return 0


# ---------------------------------------------------------------- outline

def resolve_note_arg(vault: Path, note: str, files: list[str]) -> str:
    note = note.strip().strip("/")
    if (vault / note).is_file():
        return Path(note).as_posix()
    resolver = Resolver(files)
    hit = resolver.wikilink(link_name(note) if "[[" in note else note, "")
    if hit and hit.lower().endswith(".md"):
        return hit
    raise PlanError(f"note not found: {note}")


def cmd_outline(vault: Path, note: str, as_json: bool) -> int:
    rel = resolve_note_arg(vault, note, all_md(vault))
    text, _ = read_note(vault / rel)
    data = outline_blocks(text)
    _, body, _ = split_frontmatter(text)
    data.update({"path": rel, "code_ratio": code_ratio(body)})
    if as_json:
        emit(data)
        return 0
    print(f"{rel}: {data['lines']} lines, frontmatter lines 1-{data['frontmatter_lines']}"
          if data["frontmatter_lines"] else f"{rel}: {data['lines']} lines, no frontmatter")
    print(f"code/data share: {int(data['code_ratio'] * 100)}%")
    if data["sections"]:
        print("\nSECTIONS (heading -> end of section)")
        for s in data["sections"]:
            print(f"  L{s['start']}-L{s['end']}  {'#' * s['level']} {s['heading']}")
    print("\nBLOCKS")
    for b in data["blocks"]:
        print(f"  L{b['start']}-L{b['end']}".ljust(14) + f"{b['kind']:<8} {b['preview']}")
    return 0


# ---------------------------------------------------------------- related

def tokens(text: str) -> list[str]:
    return [t.strip("'-") for t in TOKEN_RE.findall(text.lower()) if t.strip("'-") not in STOPWORDS]


def cmd_related(vault: Path, queries: list[str], top: int, plan_path: str | None) -> int:
    cfg = load_config(vault)
    files = all_md(vault)
    notes = [p for p in files if is_processable(p, cfg)]
    overlay = {}
    if plan_path:
        plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        for n in plan.get("notes", []):
            overlay[n["path"].strip("/")] = n
    docs = {}
    for rel in notes:
        try:
            text, _ = read_note(vault / rel)
        except UnicodeDecodeError:
            continue
        fm_lines, body, _ = split_frontmatter(text)
        fm = frontmatter_dict(fm_lines)
        planned = overlay.get(rel, {})
        pfm = planned.get("frontmatter", {})
        name = planned.get("title") or stem(rel)
        tags = {norm_item("tags", t) for t in as_list(fm.get("tags")) + as_list(pfm.get("tags"))} | set(inline_tags(body))
        category = pfm.get("category") or fm.get("category")
        status = pfm.get("status") or fm.get("status")
        heads = " ".join(m.group(2) for m in map(HEADING_RE.match, body.split("\n")) if m)
        toks = tokens(strip_code(body)) + tokens(name) * 3 + tokens(heads) * 2
        docs[rel] = {"name": name, "tf": Counter(toks), "tags": tags, "category": category,
                     "status": status, "links": {split_wikilink(m.group(2))[0].strip().lower()
                                                 for m in WIKILINK_RE.finditer(text)}}
    df = Counter()
    for d in docs.values():
        df.update(d["tf"].keys())
    n_docs = max(len(docs), 1)
    for d in docs.values():
        vec = {t: (1 + math.log(c)) * (math.log((n_docs + 1) / (df[t] + 1)) + 1) for t, c in d["tf"].items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        d["vec"] = {t: v / norm for t, v in vec.items()}
    archive = cfg["folders"]["archive"].lower()
    results = {}
    for q in queries:
        rel = resolve_note_arg(vault, q, files)
        if rel not in docs:
            raise PlanError(f"{rel} is not a processable note")
        me = docs[rel]
        scored = []
        for other, d in docs.items():
            if other == rel or other.lower().startswith(archive + "/") or str(d["status"]).lower() in LIFECYCLE_STATUS \
                    or is_daily(other, cfg):
                continue
            cos = sum(v * d["vec"].get(t, 0.0) for t, v in me["vec"].items())
            union = me["tags"] | d["tags"]
            jac = len(me["tags"] & d["tags"]) / len(union) if union else 0.0
            cat = 1.0 if me["category"] and str(me["category"]).lower() == str(d["category"] or "").lower() else 0.0
            score = 0.55 * cos + 0.30 * jac + 0.15 * cat
            if score <= 0.02:
                continue
            scored.append({
                "name": d["name"], "path": other, "score": round(score, 3), "text": round(cos, 3),
                "shared_tags": sorted(me["tags"] & d["tags"]), "same_category": bool(cat),
                "already_linked": d["name"].lower() in me["links"] or stem(other).lower() in me["links"],
            })
        scored.sort(key=lambda s: -s["score"])
        results[rel] = scored[:top]
    emit({"related": results, "note": "Shortlist only. Pick the 3-5 a reader would actually want next."})
    return 0


# ---------------------------------------------------------------- apply

class Note:
    def __init__(self, vault: Path, rel: str):
        self.rel = rel
        self.path = vault / rel
        self.orig_bytes = self.path.read_bytes()
        self.text, self.fmt = read_note(self.path)
        self.orig_text = self.text
        self.body_changed = False
        self.actions: list[str] = []


def plan_notes(plan: dict) -> list[dict]:
    notes = plan.get("notes")
    if not isinstance(notes, list):
        raise PlanError("plan.notes must be a list")
    return notes


def make_run_id(now: dt.datetime, vault: Path) -> str:
    base = now.strftime("%Y%m%d-%H%M%S")
    run_id, n = base, 1
    while (state_dir(vault) / "runs" / f"{run_id}.json").exists():
        n += 1
        run_id = f"{base}-{n}"
    return run_id


def cmd_apply(vault: Path, plan_path: str, dry_run: bool, now_override: str | None) -> int:
    cfg = load_config(vault)
    now = now_local(now_override)
    today = now.date().isoformat()
    stamp = now.isoformat(timespec="minutes")
    errors: list[str] = []
    warnings: list[str] = []
    if not cfg["_initialized"]:
        emit({"ok": False, "errors": ["vault not initialized: run `vault.py init VAULT` first (first-run setup)"]})
        return 1
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    entries = plan_notes(plan)
    questions = plan.get("questions") or []
    if len(entries) > cfg["batch_size"]:
        warnings.append(f"{len(entries)} notes in one plan; batches of {cfg['batch_size']} are easier to review and undo")

    files = list(walk_files(vault))
    md_files = [f for f in files if f.lower().endswith(".md")]
    resolver = Resolver(files)
    inbox = cfg["folders"]["inbox"].lower()
    loaded: dict[str, Note] = {}

    def load(rel: str) -> Note:
        if rel not in loaded:
            loaded[rel] = Note(vault, rel)
        return loaded[rel]

    def find(ref: str):
        ref = (ref or "").strip().strip("/")
        if not ref:
            return None
        if ref in md_files:
            return ref
        hit = resolver.wikilink(link_name(ref) if "[[" in ref else ref, "")
        return hit if hit and hit.lower().endswith(".md") else None

    # ---- pass 1: resolve every planned note and its final path ---------------------------
    moves: dict[str, str] = {}
    specs: list[dict] = []
    for i, entry in enumerate(entries):
        where = f"notes[{i}]"
        rel = find(entry.get("path", ""))
        if not rel:
            errors.append(f"{where}: note not found: {entry.get('path')!r}")
            continue
        if any(s["rel"] == rel for s in specs):
            errors.append(f"{where}: {rel} appears twice in the plan")
            continue
        if not is_processable(rel, cfg):
            errors.append(f"{where}: {rel} is in the meta folder or an excluded folder")
            continue
        try:
            note = load(rel)
        except UnicodeDecodeError:
            errors.append(f"{where}: {rel} is not UTF-8 text")
            continue
        fm_lines, body, fm_count = split_frontmatter(note.text)
        fm = frontmatter_dict(fm_lines)
        if str(fm.get("processor", "")).lower() == "skip":
            errors.append(f"{where}: {rel} has `processor: skip`; leave it out of the plan")
            continue
        title = (entry.get("title") or stem(rel)).strip()
        folder = entry["folder"].strip("/") if entry.get("folder") is not None else parent_dir(rel)
        if entry.get("title"):
            e, w = title_problems(title)
            errors += [f"{where}: {x}" for x in e]
            warnings += [f"{where}: {x}" for x in w]
        errors += [f"{where}: {x}" for x in folder_problems(folder)]
        if folder.split("/")[0].lower() == meta_folder(cfg).lower():
            errors.append(f"{where}: notes can't be filed into the meta folder {meta_folder(cfg)!r}")
        if is_daily(rel, cfg):
            if title != stem(rel) or folder != parent_dir(rel):
                errors.append(f"{where}: {rel} is a daily note; daily notes are never renamed or moved")
            if entry.get("splits"):
                errors.append(f"{where}: {rel} is a daily note; daily notes are never split")
        if code_ratio(body) > cfg["code_only_threshold"] and (
                entry.get("splits") or entry.get("body_edits") or entry.get("insert_top")):
            errors.append(f"{where}: {rel} is mostly code/data; add frontmatter only (no splits or edits)")
        pfm = entry.get("frontmatter") or {}
        if pfm.get("status") and pfm["status"] not in VALID_STATUS:
            errors.append(f"{where}: status {pfm['status']!r} must be one of {sorted(VALID_STATUS)}")
        if pfm.get("origin") and pfm["origin"] not in VALID_ORIGIN:
            errors.append(f"{where}: origin {pfm['origin']!r} must be one of {sorted(VALID_ORIGIN)}")
        new_rel = join_rel(folder, title + ".md")
        if new_rel != rel:
            moves[rel] = new_rel
        specs.append({"entry": entry, "rel": rel, "new_rel": new_rel, "fm": fm, "where": where,
                      "fm_count": fm_count})

    # ---- split destinations ---------------------------------------------------------------
    created: dict[str, dict] = {}
    for spec in specs:
        for j, split in enumerate(spec["entry"].get("splits") or []):
            where = f"{spec['where']}.splits[{j}]"
            mode = split.get("mode", "new")
            if mode == "append":
                target = find(split.get("target", ""))
                if not target:
                    errors.append(f"{where}: append target not found: {split.get('target')!r}")
                elif target == spec["rel"]:
                    errors.append(f"{where}: a note can't be appended to itself")
                elif not is_processable(target, cfg):
                    errors.append(f"{where}: append target {target} is in the meta folder or an excluded folder")
                else:
                    split["_dest"] = target
            elif mode == "new":
                title = (split.get("title") or "").strip()
                e, w = title_problems(title)
                errors += [f"{where}: {x}" for x in e]
                warnings += [f"{where}: {x}" for x in w]
                folder = (split.get("folder") or parent_dir(spec["new_rel"])).strip("/")
                errors += [f"{where}: {x}" for x in folder_problems(folder)]
                dest = join_rel(folder, title + ".md")
                if dest in created:
                    errors.append(f"{where}: two splits would create {dest}")
                created[dest] = {"parent": spec["rel"], "split": split}
                split["_dest"] = dest
            else:
                errors.append(f"{where}: mode must be 'new' or 'append'")

    # ---- collisions: Obsidian resolves [[links]] by name, so final names must be unique -----
    final_paths = [moves.get(f, f) for f in md_files] + list(created)
    by_name = defaultdict(list)
    for f in final_paths:
        by_name[stem(f).lower()].append(f)
    touched = set(moves.values()) | set(created)
    old_names_moving = {stem(o).lower() for o, n in moves.items() if stem(o).lower() != stem(n).lower()}
    for f in sorted(touched):
        others = [x for x in by_name[stem(f).lower()] if x != f]
        if others:
            errors.append(f"name collision: {f} vs {', '.join(others)}. Use a more specific title, "
                          f"e.g. 'Name (Category)', never 'v2'")
        old = next((o for o, n in moves.items() if n == f), None)
        if (vault / f).exists() and not (old and old.lower() == f.lower()):
            errors.append(f"{f} already exists on disk")
        if stem(f).lower() in old_names_moving and not (old and stem(old).lower() == stem(f).lower()):
            errors.append(f"{f} takes the old name of another note renamed in this run; do it in two runs")

    final_name: dict[str, str] = {}
    for f in md_files:
        final_name[stem(f).lower()] = stem(moves.get(f, f))
        final_name[stem(moves.get(f, f)).lower()] = stem(moves.get(f, f))
    for f in created:
        final_name[stem(f).lower()] = stem(f)

    def as_link(ref: str) -> str:
        name = link_name(ref)
        if name.lower() in final_name:
            return f"[[{final_name[name.lower()]}]]"
        hit = find(name)
        if hit:
            return f"[[{stem(moves.get(hit, hit))}]]"
        warnings.append(f"link target {ref!r} doesn't match any note; written as-is")
        return f"[[{name}]]"

    if errors:
        return finish(errors, warnings, [], questions, dry_run)

    # ---- pass 2: cut splits, apply edits (in memory, verbatim line ranges) -----------------
    moved_blocks: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for spec in specs:
        entry, note = spec["entry"], loaded[spec["rel"]]
        lines = note.text.split("\n")
        trailing = bool(lines) and lines[-1] == ""
        real = lines[:-1] if trailing else lines[:]
        spans = fence_spans(real)
        parent_name = stem(spec["new_rel"])
        cut: list[tuple[int, int]] = []
        blocks_here: list[tuple[int, str, str]] = []
        for split in sorted(entry.get("splits") or [], key=lambda s: -int(s.get("start", 0) or 0)):
            try:
                start, end = int(split["start"]), int(split["end"])
            except (KeyError, TypeError, ValueError):
                errors.append(f"{spec['where']}: every split needs integer start and end lines")
                continue
            if start <= spec["fm_count"] or end > len(real) or start > end:
                errors.append(f"{spec['where']}: split L{start}-L{end} is outside the note body "
                              f"(body is L{spec['fm_count'] + 1}-L{len(real)})")
                continue
            if any(not (end < a or start > b) for a, b in cut):
                errors.append(f"{spec['where']}: split L{start}-L{end} overlaps another split")
                continue
            if any(not (e < start or s > end) and not (start <= s and e <= end) for s, e in spans):
                errors.append(f"{spec['where']}: split L{start}-L{end} cuts through a code block")
                continue
            cut.append((start, end))
            chunk = real[start - 1:end]
            lead, tail = [], []
            while chunk and not chunk[0].strip():
                lead.append(chunk.pop(0))
            while chunk and not chunk[-1].strip():
                tail.insert(0, chunk.pop())
            if not chunk:
                errors.append(f"{spec['where']}: split L{start}-L{end} is empty")
                continue
            dest = split["_dest"]
            stub = f"> [!note] Moved to [[{stem(moves.get(dest, dest))}]] — {today}"
            before = [""] if start >= 2 and real[start - 2].strip() and not lead else []
            after = [""] if end < len(real) and real[end].strip() and not tail else []
            real[start - 1:end] = lead + before + [stub] + after + tail
            blocks_here.append((start, dest, "\n".join(chunk)))
        for _, dest, block in sorted(blocks_here):
            moved_blocks[dest].append((parent_name, block))
        if blocks_here:
            note.body_changed = True
            note.actions.append("split")
        fm_lines, body, _ = split_frontmatter("\n".join(real) + ("\n" if trailing else ""))
        edited = False
        for k, edit in enumerate(entry.get("body_edits") or []):
            find_text, repl = edit.get("find", ""), edit.get("replace", "")
            hits = body.count(find_text) if find_text else 0
            if hits != 1:
                errors.append(f"{spec['where']}.body_edits[{k}]: 'find' text occurs {hits} times; it must occur exactly once")
                continue
            body = body.replace(find_text, repl, 1)
            edited = True
        if entry.get("insert_top"):
            body = entry["insert_top"].rstrip("\n") + "\n\n" + body.lstrip("\n")
            edited = True
        if edited:
            note.body_changed = True
            note.actions.append("edited")
        note.text = compose(fm_lines, body)
    if errors:
        return finish(errors, warnings, [], questions, dry_run)

    new_notes: dict[str, dict] = {}
    for dest, blocks in moved_blocks.items():
        if dest in created:
            new_notes[dest] = {"text": "\n\n".join(b for _, b in blocks) + "\n",
                               "parent": created[dest]["parent"], "split": created[dest]["split"]}
        else:
            target = load(dest)
            fm_lines, body, _ = split_frontmatter(target.text)
            body = body.rstrip("\n") + "\n"
            for parent_name, block in blocks:
                body += f"\n> [!info] Moved here from [[{parent_name}]] — {today}\n\n{block}\n"
            target.text = compose(fm_lines, body)
            target.body_changed = True
            target.actions.append("appended")

    # ---- pass 3: frontmatter ---------------------------------------------------------------
    def modified_value(path, fm_before: dict, body_changed: bool):
        if body_changed or path is None:
            return today
        existing = fm_before.get("modified")
        if existing and not edited_since_processed(path, fm_before):
            return existing
        mdate = mtime_dt(path).date().isoformat()
        best = max(to_date(existing), mdate) if to_date(existing) else mdate
        return existing if to_date(existing) == best else best

    def link_fields(updates: dict, own_name: str) -> None:
        for key in LINK_KEYS:
            if not updates.get(key):
                continue
            if isinstance(updates[key], list):
                links = [as_link(v) for v in updates[key]]
                updates[key] = [l for l in dict.fromkeys(links) if link_name(l).lower() != own_name.lower()]
            else:
                updates[key] = as_link(updates[key])
        if "tags" in updates:
            updates["tags"] = list(dict.fromkeys(norm_item("tags", t) for t in as_list(updates["tags"])))

    planned = {s["rel"] for s in specs}
    for spec in specs:
        entry, note = spec["entry"], loaded[spec["rel"]]
        fm_before, old_name, new_name = spec["fm"], stem(spec["rel"]), stem(spec["new_rel"])
        updates = dict(entry.get("frontmatter") or {})
        force = set()
        updates.setdefault("title", new_name)
        if new_name != old_name and str(fm_before.get("title", "")).strip() == old_name:
            updates["title"], force = new_name, force | {"title"}
        updates.setdefault("created", created_guess(note.path, spec["rel"], fm_before))
        in_inbox = parent_dir(spec["new_rel"]).lower() in ("", inbox) and not is_daily(spec["rel"], cfg)
        updates.setdefault("status", "draft" if in_inbox else "active")
        if str(fm_before.get("status", "")).lower() == "draft" and updates["status"] == "active":
            force.add("status")
        if new_name.lower() != old_name.lower() and not JUNK_NAME_RE.match(old_name):
            updates["aliases"] = as_list(updates.get("aliases")) + [old_name]
        if updates.get("status") == "superseded" and str(fm_before.get("status")) != "superseded":
            note.actions.append("superseded")
        updates["modified"] = modified_value(note.path, fm_before, note.body_changed)
        link_fields(updates, new_name)
        fm_lines, body, _ = split_frontmatter(note.text)
        note.text = compose(merge_frontmatter(fm_lines, updates, force), body)
    for rel, note in loaded.items():
        if rel not in planned and note.body_changed:          # append targets outside the plan
            fm_lines, body, _ = split_frontmatter(note.text)
            note.text = compose(merge_frontmatter(fm_lines, {"modified": today}), body)
    for dest, info in new_notes.items():
        parent_fm = frontmatter_dict(split_frontmatter(loaded[info["parent"]].text)[0])
        updates = dict(info["split"].get("frontmatter") or {})
        updates.setdefault("title", stem(dest))
        updates.setdefault("status", "active")
        updates.setdefault("origin", parent_fm.get("origin") or "unknown")
        updates.setdefault("created", to_date(parent_fm.get("created")) or today)
        updates["modified"] = today
        updates["split_from"] = stem(moves.get(info["parent"], info["parent"]))
        link_fields(updates, stem(dest))
        info["text"] = compose(merge_frontmatter([], updates), info["text"])

    # verify before link fixing: every moved block must sit byte-for-byte in its destination
    for dest, blocks in moved_blocks.items():
        final_text = new_notes[dest]["text"] if dest in new_notes else loaded[dest].text
        for _, block in blocks:
            if block not in final_text:
                errors.append(f"internal check failed: a block moved to {dest} changed in transit")
    if errors:
        return finish(errors, warnings, [], questions, dry_run)

    # ---- pass 4: fix links everywhere (wikilinks, embeds, markdown links; never inside code) --
    link_only: set[str] = set()
    if moves:
        for rel in md_files:
            note = loaded.get(rel)
            if note is None:
                raw = (vault / rel).read_bytes()
                if b"[[" not in raw and b"](" not in raw:
                    continue
                try:
                    text = read_note(vault / rel)[0]
                except UnicodeDecodeError:
                    continue
            else:
                text = note.text
            new_text, n = rewrite_links(text, rel, moves.get(rel, rel), moves, resolver)
            if n:
                if note is None:
                    note = load(rel)
                    link_only.add(rel)
                note.text = new_text
                note.actions.append("links")
        for dest, info in new_notes.items():
            info["text"], _ = rewrite_links(info["text"], info["parent"], dest, moves, resolver)

    # ---- stamp `processed`, label actions, verify moved blocks ---------------------------------
    changed: list[str] = []
    for rel, note in loaded.items():
        new_rel = moves.get(rel, rel)
        if note.text == note.orig_text and new_rel == rel:
            continue
        fm_lines, body, _ = split_frontmatter(note.text)
        if rel not in link_only or frontmatter_dict(fm_lines).get("processed"):
            note.text = compose(merge_frontmatter(fm_lines, {"processed": stamp}), body)
        labels = []
        if parent_dir(new_rel) != parent_dir(rel):
            labels.append("moved")
        if stem(new_rel) != stem(rel):
            labels.append("renamed")
        if rel not in link_only and split_frontmatter(note.orig_text)[0] != split_frontmatter(note.text)[0] \
                and not any(a in note.actions for a in ("split", "edited", "appended", "superseded")):
            labels.append("frontmatter")
        note.actions = labels + [a for a in dict.fromkeys(note.actions)]
        changed.append(rel)
    for dest, info in new_notes.items():
        fm_lines, body, _ = split_frontmatter(info["text"])
        info["text"] = compose(merge_frontmatter(fm_lines, {"processed": stamp}), body)

    summaries = {s["rel"]: s["entry"].get("summary", "") for s in specs}
    operations = []
    for dest, info in new_notes.items():
        operations.append({"path": None, "to": dest, "actions": ["created"],
                           "summary": info["split"].get("summary")
                           or f"split out of [[{stem(moves.get(info['parent'], info['parent']))}]]"})
    for rel in changed:
        operations.append({"path": rel, "to": moves.get(rel, rel), "actions": loaded[rel].actions,
                           "summary": summaries.get(rel) or ("links updated" if rel in link_only else "")})

    if errors or dry_run:
        return finish(errors, warnings, operations, questions, dry_run)
    if not operations:
        if questions:
            append_log(vault, cfg, None, now, [], questions)
        emit({"ok": True, "run_id": None, "message": "nothing to change; the vault already matches the plan",
              "warnings": warnings, "questions": questions})
        return 0

    # ---- write: backup -> manifest -> new notes -> changed notes (then rename) -> log ----------
    run_id = make_run_id(now, vault)
    runs = state_dir(vault) / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (state_dir(vault) / "backups").mkdir(parents=True, exist_ok=True)
    backup_rel = f"{STATE_DIR}/backups/{run_id}.zip"
    with zipfile.ZipFile(vault / backup_rel, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in changed:
            zf.writestr(rel, loaded[rel].orig_bytes)
    manifest = {"run_id": run_id, "tool_version": VERSION, "started": now.isoformat(), "complete": False,
                "undone": False, "backup": backup_rel, "request": plan.get("request", ""),
                "questions": questions, "files": []}
    for dest, info in new_notes.items():
        info["bytes"] = encode_note(info["text"], {"bom": False, "nl": "\n"})
        manifest["files"].append({"op": "created", "path": dest, "sha256_after": sha256(info["bytes"])})
    for rel in changed:
        note = loaded[rel]
        note.new_bytes = encode_note(note.text, note.fmt)
        item = {"op": "modified", "path": rel, "sha256_after": sha256(note.new_bytes)}
        if moves.get(rel, rel) != rel:
            item.update(op="moved", to=moves[rel])
        manifest["files"].append(item)
    manifest_path = runs / f"{run_id}.json"
    atomic_write(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False).encode())

    for dest, info in new_notes.items():
        atomic_write(vault / dest, info["bytes"])
    for rel in changed:
        note = loaded[rel]
        atomic_write(note.path, note.new_bytes)
        new_rel = moves.get(rel, rel)
        if new_rel != rel:
            target = vault / new_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if rel.lower() == new_rel.lower():           # case-only rename on case-insensitive disks
                tmp = note.path.with_name(f".op-rename-{run_id}")
                os.rename(note.path, tmp)
                os.rename(tmp, target)
            else:
                os.rename(note.path, target)

    append_log(vault, cfg, run_id, now, operations, questions)
    manifest["complete"] = True
    manifest["finished"] = now_local().isoformat()
    atomic_write(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False).encode())
    emit({"ok": True, "run_id": run_id, "warnings": warnings, "operations": operations,
          "questions": questions, "log": log_path(vault, cfg).relative_to(vault).as_posix(),
          "undo": f"vault.py undo \"{vault}\" --run {run_id}"})
    return 0


def finish(errors, warnings, operations, questions, dry_run) -> int:
    emit({"ok": not errors, "dry_run": dry_run, "errors": errors, "warnings": warnings,
          "operations": operations, "questions": questions})
    return 1 if errors else 0


# ---------------------------------------------------------------- log

def cell(text: str) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


def append_log(vault: Path, cfg: dict, run_id, now: dt.datetime, operations: list[dict], questions: list[str],
               heading: str | None = None) -> None:
    lp = log_path(vault, cfg)
    if lp.exists():
        text, fmt = read_note(lp)
    else:
        text = LOG_TEMPLATE.format(today=now.date().isoformat(), needs=NEEDS_HEADING + "\n", marker=RUNS_MARKER)
        fmt = {"bom": False, "nl": "\n"}
    if questions:
        items = "".join(f"- [ ] ({run_id or now.strftime('%Y%m%d')}) {q}\n" for q in questions)
        if NEEDS_HEADING in text:
            idx = text.index(NEEDS_HEADING) + len(NEEDS_HEADING)
            nl = text.find("\n", idx)
            nl = len(text) if nl == -1 else nl + 1
            text = text[:nl] + items + text[nl:]
        else:
            text = text.rstrip("\n") + f"\n\n{NEEDS_HEADING}\n{items}"
    if operations or heading:
        title = heading or f"## {now.strftime('%Y-%m-%d %H:%M')} — run {run_id} ({len(operations)} notes)"
        block = [title, "", "| Time | Action | Note | From → To | Summary |", "|---|---|---|---|---|"]
        for op in operations:
            to = op.get("to")
            name = f"[[{stem(to)}]]" if to and to.lower().endswith(".md") else cell(to or "")
            src = op.get("path")
            if src and to and src != to:
                where = f"`{cell(src)}` → `{cell(to)}`"
            elif to and not src:
                where = f"new: `{cell(to)}`"
            else:
                where = f"`{cell(src or to)}`"
            block.append(f"| {now.strftime('%H:%M')} | {', '.join(op.get('actions', []))} | {name} | {where} | {cell(op.get('summary'))} |")
        if run_id and not heading:
            block += ["", f"Undo: tell Claude **\"undo obsidian-processor run {run_id}\"**."]
        rendered = "\n".join(block) + "\n"
        if RUNS_MARKER in text:
            idx = text.index(RUNS_MARKER) + len(RUNS_MARKER)
            text = text[:idx] + "\n\n" + rendered + text[idx:].lstrip("\n") and \
                text[:idx] + "\n\n" + rendered + ("\n" + text[idx:].lstrip("\n") if text[idx:].strip() else "")
        else:
            text = text.rstrip("\n") + "\n\n" + rendered
    atomic_write(lp, encode_note(text, fmt))


# ---------------------------------------------------------------- undo

def cmd_undo(vault: Path, run_id: str | None, force: bool) -> int:
    cfg = load_config(vault)
    runs_dir = state_dir(vault) / "runs"
    manifests = sorted(runs_dir.glob("*.json")) if runs_dir.exists() else []
    loaded = [json.loads(p.read_text(encoding="utf-8")) for p in manifests]
    active = [m for m in loaded if not m.get("undone")]
    if not active:
        emit({"ok": False, "errors": ["no runs to undo"]})
        return 1
    target = active[-1] if run_id in (None, "", "last") else next((m for m in loaded if m["run_id"] == run_id), None)
    if target is None:
        emit({"ok": False, "errors": [f"run {run_id} not found"], "runs": [m["run_id"] for m in loaded]})
        return 1
    if target.get("undone"):
        emit({"ok": False, "errors": [f"run {target['run_id']} was already undone"]})
        return 1
    later = [m["run_id"] for m in active if m["run_id"] > target["run_id"]]
    if later and not force:
        emit({"ok": False, "errors": [f"later runs exist ({', '.join(later)}); undo those first, newest first"]})
        return 1
    conflicts = []
    for f in target["files"]:
        current = vault / (f.get("to") or f["path"])
        if current.exists() and sha256(current.read_bytes()) != f["sha256_after"]:
            conflicts.append((f.get("to") or f["path"]) + " changed since the run")
        if not current.exists():
            conflicts.append((f.get("to") or f["path"]) + " is missing")
        if f["op"] == "moved" and (vault / f["path"]).exists() and f["path"].lower() != f["to"].lower():
            conflicts.append(f"{f['path']} exists again; restoring would overwrite it")
    if conflicts and not force:
        emit({"ok": False, "errors": conflicts,
              "hint": "nothing was changed. Re-run with --force to restore originals anyway (edits made since the run are lost)"})
        return 1
    zf = zipfile.ZipFile(vault / target["backup"])
    restored, removed = [], []
    for f in reversed(target["files"]):
        if f["op"] == "created":
            p = vault / f["path"]
            if p.exists() and (force or sha256(p.read_bytes()) == f["sha256_after"]):
                p.unlink()
                removed.append(f["path"])
        elif f["op"] == "moved":
            p = vault / f["to"]
            if p.exists():
                p.unlink()
            atomic_write(vault / f["path"], zf.read(f["path"]))
            restored.append(f"{f['to']} → {f['path']}")
        else:
            atomic_write(vault / f["path"], zf.read(f["path"]))
            restored.append(f["path"])
    zf.close()
    target["undone"] = True
    target["undone_at"] = now_local().isoformat()
    atomic_write(runs_dir / f"{target['run_id']}.json", json.dumps(target, indent=2, ensure_ascii=False).encode())
    now = now_local()
    ops = [{"path": None, "to": r, "actions": ["restored"], "summary": ""} for r in restored] + \
          [{"path": None, "to": r, "actions": ["removed (created by run)"], "summary": ""} for r in removed]
    append_log(vault, cfg, target["run_id"], now, ops, [],
               heading=f"## {now.strftime('%Y-%m-%d %H:%M')} — undo of run {target['run_id']}")
    emit({"ok": True, "undone": target["run_id"], "restored": restored, "removed": removed})
    return 0


# ---------------------------------------------------------------- check

def cmd_check(vault: Path, as_json: bool) -> int:
    cfg = load_config(vault)
    files = list(walk_files(vault))
    md_files = [f for f in files if f.lower().endswith(".md")]
    resolver = Resolver(files)
    broken, no_fm, names = [], [], defaultdict(list)
    for rel in md_files:
        names[stem(rel).lower()].append(rel)
        try:
            text, _ = read_note(vault / rel)
        except UnicodeDecodeError:
            continue
        fm_lines, _, _ = split_frontmatter(text)
        if fm_lines is None and is_processable(rel, cfg):
            no_fm.append(rel)
        regions = code_regions(text)
        for m in WIKILINK_RE.finditer(text):
            if in_regions(m.start(), regions):
                continue
            target = split_wikilink(m.group(2))[0].strip()
            if target and not resolver.wikilink(target, rel):
                broken.append({"file": rel, "link": m.group(0)})
        for m in MDLINK_RE.finditer(text):
            if in_regions(m.start(), regions):
                continue
            raw = m.group(2).strip("<>")
            if re.match(r"^[a-z][a-z0-9+.\-]*:", raw, re.I) or raw.startswith("#"):
                continue
            decoded = urllib.parse.unquote(raw.partition("#")[0])
            if decoded and not resolver.mdlink(decoded, rel):
                broken.append({"file": rel, "link": m.group(0)})
    dupes = {k: v for k, v in names.items() if len(v) > 1}
    loose = [f for f in md_files if "/" not in f and is_processable(f, cfg)]
    result = {
        "ok": True,
        "notes": len(md_files),
        "broken_links": len(broken),
        "duplicate_names": len(dupes),
        "missing_frontmatter": len(no_fm),
        "loose_in_root": len(loose),
        "details": {"broken_links": broken[:200], "duplicate_names": dupes,
                    "missing_frontmatter": no_fm[:50], "loose_in_root": loose[:50]},
    }
    if as_json:
        emit(result)
    else:
        print(f"notes: {result['notes']}  broken links: {result['broken_links']}  duplicate names: "
              f"{result['duplicate_names']}  missing frontmatter: {result['missing_frontmatter']}  "
              f"loose in root: {result['loose_in_root']}")
        for b in broken[:50]:
            print(f"  broken: {b['file']}: {b['link']}")
        for k, v in list(dupes.items())[:20]:
            print(f"  duplicate name: {', '.join(v)}")
    return 0


# ---------------------------------------------------------------- cli

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="vault.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("--version", action="version", version=f"obsidian-processor vault.py {VERSION}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="first-run setup: config, folders, log, dashboard")
    p.add_argument("vault")
    p.add_argument("--config-json", help="JSON merged into the config (e.g. folder names)")

    p = sub.add_parser("scan", help="index notes as JSON")
    p.add_argument("vault")
    p.add_argument("--scope", choices=["changed", "inbox", "all"], default="changed")
    p.add_argument("--paths", nargs="*")
    p.add_argument("--out")

    p = sub.add_parser("outline", help="numbered blocks and sections of one note")
    p.add_argument("vault")
    p.add_argument("note")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("related", help="shortlist related notes")
    p.add_argument("vault")
    p.add_argument("notes", nargs="+")
    p.add_argument("--top", type=int, default=8)
    p.add_argument("--plan")

    p = sub.add_parser("apply", help="execute a PLAN.json (backup, split, frontmatter, move, links, log)")
    p.add_argument("vault")
    p.add_argument("plan")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--now", help="ISO timestamp to use instead of the clock (tests)")

    p = sub.add_parser("undo", help="reverse a run")
    p.add_argument("vault")
    p.add_argument("--run", help="run id (default: the latest)")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("check", help="broken links, duplicate names, missing frontmatter")
    p.add_argument("vault")
    p.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    vault = Path(args.vault).expanduser().resolve()
    if not vault.is_dir():
        emit({"ok": False, "errors": [f"vault folder not found: {vault}"]})
        return 1
    try:
        if args.cmd == "init":
            return cmd_init(vault, args.config_json)
        if args.cmd == "scan":
            return cmd_scan(vault, args.scope, args.paths, args.out)
        if args.cmd == "outline":
            return cmd_outline(vault, args.note, args.json)
        if args.cmd == "related":
            return cmd_related(vault, args.notes, args.top, args.plan)
        if args.cmd == "apply":
            return cmd_apply(vault, args.plan, args.dry_run, args.now)
        if args.cmd == "undo":
            return cmd_undo(vault, args.run, args.force)
        if args.cmd == "check":
            return cmd_check(vault, args.json)
    except PlanError as exc:
        emit({"ok": False, "errors": [str(exc)]})
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
