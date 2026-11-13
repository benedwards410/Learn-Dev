"""Tests for skills/obsidian-processor/scripts/vault.py.

Run from the repo root:  python3 -m unittest discover -s tests -v
"""
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "obsidian-processor" / "scripts"))
import vault  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "vault"
PLAN = ROOT / "tests" / "fixtures" / "plan-triage.json"
MTIMES = json.loads((ROOT / "tests" / "fixtures" / "mtimes.json").read_text())
UPLOADED = "Create plan for new  skill generation- organize obsidian.md"


def run(*args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = vault.main([str(a) for a in args])
    out = buf.getvalue()
    try:
        return code, json.loads(out)
    except json.JSONDecodeError:
        return code, out


def tree_hashes(root: Path, skip=(".obsidian-processor", "99-Meta")):
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_file() and not rel.startswith(skip):
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def lines_of(path: Path, start: int, end: int) -> str:
    return "\n".join(path.read_text(encoding="utf-8").split("\n")[start - 1:end])


class VaultCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="op-test-"))
        self.v = self.tmp / "vault"
        shutil.copytree(FIXTURE, self.v)
        for rel, stamp in MTIMES.items():
            t = dt.datetime.fromisoformat(stamp).timestamp()
            os.utime(self.v / rel, (t, t))
        self.today = dt.date.today().isoformat()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def init(self):
        code, out = run("init", self.v)
        self.assertEqual(code, 0, out)

    def apply(self, plan_path=PLAN, dry=False):
        args = ["apply", self.v, plan_path] + (["--dry-run"] if dry else [])
        return run(*args)

    def write_plan(self, plan: dict) -> Path:
        p = self.tmp / f"plan-{len(list(self.tmp.glob('plan-*')))}.json"
        p.write_text(json.dumps(plan), encoding="utf-8")
        return p


class ScanAndOutline(VaultCase):
    def test_scan_flags(self):
        code, out = run("scan", self.v, "--scope", "all")
        self.assertEqual(code, 0)
        notes = {n["path"]: n for n in out["notes"]}
        self.assertNotIn("Templates/Meeting.md", notes, "template folder from .obsidian/templates.json is excluded")
        self.assertEqual(out["counts"]["notes"], 12)
        self.assertTrue(notes["embedder snippet.md"]["mostly_code"])
        self.assertTrue(notes["2026-11-01.md"]["daily_note"])
        self.assertEqual(notes["Reading List.md"]["created_guess"], "2025-01-15")
        self.assertEqual(notes["kce notes final v2.md"]["created_guess"], "2026-10-30")
        self.assertTrue(all(n["needs_processing"] for n in notes.values()))
        self.assertFalse(out["initialized"])

    def test_outline_sections(self):
        code, out = run("outline", self.v, "kce notes final v2", "--json")
        self.assertEqual(code, 0)
        ff = [s for s in out["sections"] if s["heading"] == "Fantasy football"][0]
        self.assertEqual((ff["start"], ff["end"]), (15, 23))

    def test_related_finds_duplicate(self):
        code, out = run("related", self.v, "Python.md")
        self.assertEqual(code, 0)
        top = out["related"]["Python"][0]
        self.assertEqual(top["path"], "File types for parsing.md")

    def test_related_unknown_name_is_per_note(self):
        code, out = run("related", self.v, "Python.md", "No Such Note")
        self.assertIn("Python", out["related"])
        self.assertTrue(any("No Such Note" in e for e in out["errors"]))

    def test_related_sees_planned_splits(self):
        run("init", self.v)
        code, out = run("related", self.v, "RAG Pipeline litellm Prompt", "Fantasy Football", "--plan", PLAN)
        self.assertEqual(code, 0, out)
        self.assertTrue(out["related"]["RAG Pipeline litellm Prompt"], "planned split note can be scored")
        ff = [r["name"] for r in out["related"]["Fantasy Football"]]
        self.assertNotIn("KCE Ops Notes", ff[:1], "fantasy section no longer counted inside the KCE note")

    def test_horizontal_rule_is_not_frontmatter(self):
        fm, body, n = vault.split_frontmatter("---\nJust a rule\n\nText\n---\nMore\n")
        self.assertIsNone(fm)
        self.assertEqual(n, 0)


class FrontmatterMerge(unittest.TestCase):
    def test_user_fields_win_and_lists_union(self):
        fm = ["title: My Title", "created: 2024-01-01", "status: active", "tags: [books]", "modified: 2024-02-02"]
        merged = vault.merge_frontmatter(fm, {
            "title": "Other", "created": "2026-01-01", "status": "draft",
            "tags": ["books", "reading"], "modified": "2026-11-13", "category": "Books",
        })
        data = vault.frontmatter_dict(merged)
        self.assertEqual(data["title"], "My Title")
        self.assertEqual(data["created"], "2024-01-01")
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["tags"], ["books", "reading"])
        self.assertEqual(data["modified"], "2026-11-13")
        self.assertEqual(data["category"], "Books")
        self.assertEqual(merged[0], "title: My Title", "existing lines keep their order")

    def test_lifecycle_status_overrides(self):
        merged = vault.merge_frontmatter(["status: active"], {"status": "superseded"})
        self.assertEqual(vault.frontmatter_dict(merged)["status"], "superseded")

    def test_quoting(self):
        self.assertEqual(vault.yaml_scalar("[[Note]]"), '"[[Note]]"')
        self.assertEqual(vault.yaml_scalar("a: b"), '"a: b"')
        self.assertEqual(vault.yaml_scalar("2026-11-13"), "2026-11-13")
        self.assertEqual(vault.yaml_scalar("yes"), '"yes"')


class ApplyTriage(VaultCase):
    def setUp(self):
        super().setUp()
        self.init()
        self.before = tree_hashes(self.v)
        self.ff_block = lines_of(self.v / "kce notes final v2.md", 15, 23)
        self.rag_block = lines_of(self.v / UPLOADED, 121, 193).strip("\n")
        code, self.out = self.apply()
        self.assertEqual(code, 0, self.out)

    def read(self, rel):
        return (self.v / rel).read_text(encoding="utf-8")

    def test_files_filed_and_renamed(self):
        for rel in ["20-Areas/KCE Ops Notes.md", "20-Areas/Fantasy Football.md",
                    "10-Projects/Obsidian Processor Skill Plan.md",
                    "30-Reference/RAG Pipeline/RAG Pipeline litellm Prompt.md",
                    "30-Reference/RAG Pipeline/RAG File Types and Embedding.md",
                    "90-Archive/File Types for Parsing.md", "00-Inbox/Untitled 3.md", "2026-11-01.md"]:
            self.assertTrue((self.v / rel).exists(), rel)
        for rel in ["kce notes final v2.md", "Python.md", UPLOADED, "File types for parsing.md"]:
            self.assertFalse((self.v / rel).exists(), rel)
        self.assertTrue((self.v / "Templates/Meeting.md").exists())

    def test_split_append_is_verbatim(self):
        kce = self.read("20-Areas/KCE Ops Notes.md")
        self.assertIn(f"> [!note] Moved to [[Fantasy Football]] — {self.today}", kce)
        self.assertNotIn("League draft is Sept 3", kce)
        ff = self.read("20-Areas/Fantasy Football.md")
        self.assertIn(self.ff_block, ff)
        self.assertIn(f"> [!info] Moved here from [[KCE Ops Notes]] — {self.today}", ff)
        self.assertIn("12-team PPR league", ff, "existing content kept")

    def test_split_new_note_is_verbatim(self):
        new = self.read("30-Reference/RAG Pipeline/RAG Pipeline litellm Prompt.md")
        body = vault.split_frontmatter(new)[1]
        self.assertEqual(hashlib.sha256(body.strip("\n").encode()).hexdigest(),
                         hashlib.sha256(self.rag_block.encode()).hexdigest())
        fm = vault.frontmatter_dict(vault.split_frontmatter(new)[0])
        self.assertEqual(fm["split_from"], "[[Obsidian Processor Skill Plan]]")
        self.assertEqual(fm["origin"], "llm")
        parent = self.read("10-Projects/Obsidian Processor Skill Plan.md")
        self.assertIn("[[RAG Pipeline litellm Prompt]]", parent)
        self.assertNotIn("litellm is the only model interface", parent)
        self.assertEqual(vault.frontmatter_dict(vault.split_frontmatter(parent)[0])["origin"], "mixed")

    def test_every_link_form_rewritten(self):
        self.assertIn("[[KCE Ops Notes#Billing]]", self.read("20-Areas/Matrix Billing.md"))
        self.assertIn("[[KCE Ops Notes|KCE notes]]", self.read("20-Areas/Matrix Billing.md"))
        self.assertIn("![[KCE Ops Notes#Closeout]]", self.read("20-Areas/Contractors.md"))
        self.assertIn("[[KCE Ops Notes]]", self.read("2026-11-01.md"))
        review = self.read("20-Areas/Weekly Review.md")
        self.assertIn("[KCE note](KCE%20Ops%20Notes.md)", review)
        self.assertIn("`[[kce notes final v2]]`", review, "inline code untouched")
        self.assertIn("[[kce notes final v2]] inside a code block", review, "fenced code untouched")

    def test_no_new_broken_links(self):
        code, out = run("check", self.v, "--json")
        self.assertEqual(out["broken_links"], 1, out["details"]["broken_links"])   # pre-existing [[wikilinks]]
        self.assertEqual(out["duplicate_names"], 0)

    def test_frontmatter_rules(self):
        reading = vault.frontmatter_dict(vault.split_frontmatter(self.read("20-Areas/Reading List.md"))[0])
        self.assertEqual(reading["created"], "2025-01-15")
        self.assertEqual(reading["tags"], ["books", "reading"])
        kce = vault.frontmatter_dict(vault.split_frontmatter(self.read("20-Areas/KCE Ops Notes.md"))[0])
        self.assertEqual(kce["created"], "2026-10-30")
        self.assertEqual(kce["modified"], self.today, "body changed by the split")
        self.assertEqual(kce["aliases"], ["kce notes final v2"])
        billing = vault.frontmatter_dict(vault.split_frontmatter(self.read("20-Areas/Matrix Billing.md"))[0])
        self.assertEqual(billing["modified"], "2026-09-12", "frontmatter-only change keeps last real edit")
        old = vault.frontmatter_dict(vault.split_frontmatter(self.read("90-Archive/File Types for Parsing.md"))[0])
        self.assertEqual(old["status"], "superseded")
        self.assertEqual(old["superseded_by"], "[[RAG File Types and Embedding]]")
        self.assertNotIn("aliases", old, "case-only rename adds no alias")
        daily = vault.frontmatter_dict(vault.split_frontmatter(self.read("2026-11-01.md"))[0])
        self.assertEqual(daily["status"], "active")
        inbox = vault.frontmatter_dict(vault.split_frontmatter(self.read("00-Inbox/Untitled 3.md"))[0])
        self.assertEqual(inbox["status"], "draft")
        self.assertNotIn("aliases", inbox)
        snippet = self.read("30-Reference/RAG Pipeline/Embedder Snippet.md")
        self.assertEqual(vault.split_frontmatter(snippet)[1],
                         (FIXTURE / "embedder snippet.md").read_text(), "mostly-code note body untouched")

    def test_log_written(self):
        log = self.read("99-Meta/Processing Log.md")
        self.assertIn(f"run {self.out['run_id']}", log)
        self.assertIn("[[KCE Ops Notes]]", log)
        self.assertIn("- [ ] (" + self.out["run_id"] + ") What is [[Untitled 3]] about", log)
        self.assertTrue((self.v / "99-Meta/Vault Dashboard.md").exists())

    def test_second_run_changes_nothing(self):
        plan = json.loads(PLAN.read_text())
        moved = {o["path"]: o["to"] for o in self.out["operations"] if o["path"]}
        for n in plan["notes"]:
            n["path"] = moved.get(n["path"], n["path"])
            n.pop("splits", None)
        code, out = self.apply(self.write_plan(plan))
        self.assertEqual(code, 0, out)
        self.assertIsNone(out["run_id"], out.get("operations"))

    def test_scan_changed_skips_processed_daily_and_inbox(self):
        code, out = run("scan", self.v)
        paths = [n["path"] for n in out["notes"]]
        self.assertNotIn("2026-11-01.md", paths)
        self.assertNotIn("00-Inbox/Untitled 3.md", paths)
        code, out = run("check", self.v, "--json")
        self.assertEqual(out["loose_in_root"], 0, "daily notes don't count as loose")

    def test_manifest_records_plan(self):
        manifest = json.loads((self.v / ".obsidian-processor/runs" / f"{self.out['run_id']}.json").read_text())
        self.assertEqual(manifest["plan"], str(PLAN.resolve()))
        self.assertTrue(manifest["complete"])

    def test_undo_restores_byte_identical(self):
        code, out = run("undo", self.v)
        self.assertEqual(code, 0, out)
        self.assertEqual(tree_hashes(self.v), self.before)
        self.assertIn("undo of run", self.read("99-Meta/Processing Log.md"))
        code, out = run("undo", self.v)
        self.assertNotEqual(code, 0, "nothing left to undo")

    def test_undo_refuses_after_user_edit(self):
        target = self.v / "20-Areas/Matrix Billing.md"
        target.write_text(target.read_text() + "\nmy new line\n")
        code, out = run("undo", self.v)
        self.assertNotEqual(code, 0)
        self.assertIn("changed since the run", " ".join(out["errors"]))
        self.assertIn("my new line", target.read_text(), "nothing was touched")


class PlanValidation(VaultCase):
    def setUp(self):
        super().setUp()
        self.init()

    def expect_error(self, plan: dict, fragment: str):
        code, out = self.apply(self.write_plan(plan), dry=True)
        self.assertNotEqual(code, 0, out)
        self.assertTrue(any(fragment in e for e in out["errors"]), out["errors"])

    def test_version_words_rejected(self):
        self.expect_error({"notes": [{"path": "Python.md", "title": "Python v2"}]}, "version word")

    def test_bad_characters_rejected(self):
        self.expect_error({"notes": [{"path": "Python.md", "title": "Python: notes"}]}, "characters")

    def test_name_collision_rejected(self):
        self.expect_error({"notes": [{"path": "Python.md", "title": "Matrix Billing", "folder": "30-Reference"}]},
                          "name collision")

    def test_daily_note_never_renamed(self):
        self.expect_error({"notes": [{"path": "2026-11-01.md", "title": "Vault Work"}]}, "daily note")

    def test_split_through_code_rejected(self):
        self.expect_error({"notes": [{"path": "Python.md", "splits": [
            {"start": 18, "end": 21, "mode": "new", "title": "Embedder Code"}]}]}, "code block")

    def test_mostly_code_note_not_split(self):
        self.expect_error({"notes": [{"path": "embedder snippet.md", "splits": [
            {"start": 1, "end": 3, "mode": "new", "title": "Imports"}]}]}, "mostly code")

    def test_split_inside_frontmatter_rejected(self):
        self.expect_error({"notes": [{"path": "Reading List.md", "splits": [
            {"start": 2, "end": 7, "mode": "new", "title": "Books"}]}]}, "outside the note body")

    def test_processor_skip_respected(self):
        p = self.v / "Python.md"
        p.write_text("---\nprocessor: skip\n---\n" + p.read_text())
        self.expect_error({"notes": [{"path": "Python.md", "folder": "30-Reference"}]}, "processor: skip")

    def expect_warning(self, plan: dict, fragment: str):
        code, out = self.apply(self.write_plan(plan), dry=True)
        self.assertEqual(code, 0, out)
        self.assertTrue(any(fragment in w for w in out["warnings"]), out["warnings"])
        return out

    def test_unknown_keys_rejected(self):
        self.expect_error({"notes": [{"path": "Python.md", "fronmatter": {}}]}, "unknown keys")
        self.expect_error({"notes": [{"path": "kce notes final v2.md", "splits": [
            {"start": 15, "end": 23, "mode": "append", "target": "Fantasy Football", "tittle": "x"}]}]}, "unknown keys")

    def test_unresolvable_related_rejected(self):
        self.expect_error({"notes": [{"path": "Python.md", "frontmatter": {"related": ["Does Not Exist"]}}]},
                          "broken link")

    def test_batch_limit(self):
        self.expect_error({"notes": [{"path": "Python.md"}] * 26}, "the limit is 25")

    def test_tags_cleaned(self):
        out = self.expect_warning({"notes": [{"path": "Python.md", "frontmatter": {"tags": ["#RAG", "Two Words"]}}]},
                                  "two-words")
        self.assertEqual(out["operations"][0]["frontmatter"]["tags"], ["rag", "two-words"])

    def test_category_reuses_vault_spelling(self):
        (self.v / "Reading List.md").write_text("---\ncategory: Books\n---\n# Reading List\n")
        out = self.expect_warning({"notes": [{"path": "Python.md", "frontmatter": {"category": "books"}}]},
                                  "existing 'Books'")
        self.assertEqual(out["operations"][0]["frontmatter"]["category"], "Books")

    def test_thin_subfolder_and_small_split_warn(self):
        self.expect_warning({"notes": [{"path": "Reading List.md", "folder": "20-Areas/Books"}]}, "subfolder")
        self.expect_warning({"notes": [{"path": "kce notes final v2.md", "splits": [
            {"start": 25, "end": 26, "mode": "new", "title": "Follow Ups", "folder": "20-Areas"}]}]}, "split threshold")

    def test_collision_reported_once(self):
        code, out = self.apply(self.write_plan(
            {"notes": [{"path": "Python.md", "title": "matrix billing"}]}), dry=True)
        self.assertEqual(sum("name collision" in e for e in out["errors"]), 1, out["errors"])

    def test_requires_init(self):
        shutil.rmtree(self.v / ".obsidian-processor")
        self.expect_error({"notes": []}, "not initialized")


class PlanSchema(unittest.TestCase):
    def test_plans_match_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        schema = json.loads((ROOT / "skills/obsidian-processor/assets/plan.schema.json").read_text())
        for path in (PLAN, ROOT / "skills/obsidian-processor/assets/plan-example.json"):
            jsonschema.validate(json.loads(path.read_text()), schema)


class EdgeCases(VaultCase):
    def setUp(self):
        super().setUp()
        self.init()

    def test_crlf_and_path_links(self):
        (self.v / "Win Note.md").write_bytes(b"# Win\r\n\r\nSee [[Python]] and [[./Python.md|py]].\r\n")
        plan = {"notes": [{"path": "Python.md", "title": "RAG Parsing", "folder": "30-Reference"}]}
        code, out = self.apply(self.write_plan(plan))
        self.assertEqual(code, 0, out)
        data = (self.v / "Win Note.md").read_bytes()
        self.assertIn(b"\r\n", data)
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
        self.assertIn(b"[[RAG Parsing]]", data)
        self.assertIn(b"[[30-Reference/RAG Parsing.md|py]]", data)

    def test_edit_request_insert_top(self):
        plan = {"notes": [{"path": "Python.md", "insert_top": "**In plain English:** the parser reads five file types.",
                           "frontmatter": {"origin": "mixed"}}]}
        code, out = self.apply(self.write_plan(plan))
        self.assertEqual(code, 0, out)
        text = (self.v / "Python.md").read_text()
        body = vault.split_frontmatter(text)[1]
        self.assertTrue(body.startswith("**In plain English:**"))
        self.assertIn((FIXTURE / "Python.md").read_text(), body, "rest untouched")
        self.assertIn("edited", out["operations"][0]["actions"])


if __name__ == "__main__":
    unittest.main()
