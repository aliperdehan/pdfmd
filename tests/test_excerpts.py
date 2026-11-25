"""P1b record commands; all sources and passages here are invented."""
from __future__ import annotations

import json
import copy
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd  # noqa: E402


def has_poppler_pdftotext():
    program = shutil.which("pdftotext")
    if not program:
        return False
    try:
        result = subprocess.run([program, "-v"], capture_output=True, encoding="utf-8", errors="replace", timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and "poppler" in (result.stdout + result.stderr).casefold()


POPPLER_PDFTOTEXT = has_poppler_pdftotext()


class CommandFixture:
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="excerpts-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = ""

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def raw(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--excerpts", *args],
                              cwd=self.root, env={**os.environ, "PDFMD_CONFIG": self.config, "PDFMD_NO_PROMPT": "1"},
                              capture_output=True, encoding="utf-8", timeout=60)

    def command(self, *args, code=0):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--excerpts", *args, "--json"],
                                cwd=self.root, env={**os.environ, "PDFMD_CONFIG": self.config, "PDFMD_NO_PROMPT": "1"},
                                capture_output=True, encoding="utf-8", timeout=60)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)


class Commands(CommandFixture, unittest.TestCase):
    def test_renumber_rewrites_unambiguous_markers_after_a_merge(self):
        record = self.write("excerpts.json", json.dumps({
            "pdfmd-excerpts": 1, "next-id": 3, "sources": {}, "excerpts": [
                {"id": 1, "key": "glass", "page": "41", "kind": "text", "parts": []},
                {"id": 1, "key": "clay", "page": "52", "kind": "text", "parts": []},
                {"id": 2, "key": "glass", "page": "42", "kind": "text", "parts": []},
            ]}))
        path = self.write("draft.md", "Ambiguous [@x:1].\n")
        before = record.read_bytes()
        report = self.command("check", code=1)
        self.assertEqual([item["code"] for item in report], ["excerpt-file"])
        self.assertIn("duplicate excerpt id 1", report[0]["message"])
        self.assertIn("ambiguous", self.command("renumber", code=1)["error"])
        self.assertEqual(record.read_bytes(), before)
        self.assertEqual(path.read_text(encoding="utf-8"), "Ambiguous [@x:1].\n")
        path.write_bytes(b"One [@glass:1] and [@clay#1] with `@clay#1`.\r\n")
        answer = self.command("renumber")
        self.assertEqual({(item["key"], item["new"]) for item in answer["renumbered"]}, {("glass", 3), ("clay", 4)})
        self.assertEqual(path.read_bytes(), b"One [@glass#3] and [@clay#4] with `@clay#1`.\r\n")
        self.assertEqual(json.loads(record.read_bytes())["next-id"], 5)

    def test_rekey_updates_source_and_long_markers(self):
        record = self.write("excerpts.json", json.dumps({
            "pdfmd-excerpts": 1, "next-id": 2, "sources": {"glass": {"future": 1}}, "excerpts": [
                {"id": 1, "key": "glass", "page": "41", "kind": "text", "parts": []}]}))
        path = self.write("draft.md", "[@glass:1] [@x#1] and `@glass#1`.\n")
        meta = self.write("metadata.yaml", "nocite: '[@glass#1]'\nreferences:\n  - id: 'glass'\n    title: '@glass#1'\n")
        other = self.write("other/draft.md", "[@glass#1].\n")
        self.write("other/excerpts.json", record.read_text(encoding="utf-8"))
        self.command("rekey", "glass", "glasswork")
        self.assertEqual(path.read_text(encoding="utf-8"), "[@glasswork#1] [@x#1] and `@glass#1`.\n")
        self.assertEqual(meta.read_text(encoding="utf-8"),
                         "nocite: '[@glasswork#1]'\nreferences:\n  - id: 'glass'\n    title: '@glass#1'\n")
        self.assertEqual(other.read_text(encoding="utf-8"), "[@glass#1].\n")
        data = json.loads(record.read_bytes())
        self.assertEqual(data["sources"], {"glasswork": {"future": 1}})
        self.assertEqual(data["excerpts"][0]["key"], "glasswork")

    def test_repairs_roll_back_markdown_if_record_write_fails(self):
        from pdfmd_excerpts.repairs import rekey

        path = self.write("draft.md", "[@glass#1].\n")
        self.command("add", "--key", "glass", "--page", "41")
        record = self.root / "excerpts.json"
        before = record.read_bytes()
        write = pdfmd.atomic_write_bytes

        def fail_record(destination, data):
            if destination == record.resolve():
                raise OSError("synthetic record write failure")
            write(destination, data)

        with mock.patch.object(pdfmd, "atomic_write_bytes", side_effect=fail_record):
            with self.assertRaisesRegex(OSError, "synthetic record write failure"):
                rekey(self.root, record.resolve(), "glass", "glasswork")
        self.assertEqual(path.read_text(encoding="utf-8"), "[@glass#1].\n")
        self.assertEqual(record.read_bytes(), before)

    def test_list_defaults_to_aligned_record_fields_and_keeps_full_json(self):
        records = [
            {"id": 2, "kind": "remark", "note": "Remark canary"},
            {"id": 1, "key": "glass", "page": "iv", "kind": "area", "label": "Table\n4", "locator": "ch. 3",
             "file": "si", "created": "2026-11-18", "quoting": "Quotation canary", "note": "Note canary",
             "parts": [{"text": "Passage canary"}], "future": "Extension canary"},
        ]
        self.write("excerpts.json", json.dumps({"pdfmd-excerpts": 1, "next-id": 3, "sources": {}, "excerpts": records}))
        plain = self.raw("list")
        self.assertEqual(plain.returncode, 0, plain.stderr)
        header, first, second = plain.stdout.splitlines()
        self.assertEqual(header.split(), ["id", "key", "page", "kind", "locator", "label", "file", "created"])
        for column, value in (("id", "1"), ("key", "glass"), ("page", "iv"), ("kind", "area"),
                              ("locator", "ch. 3"), ("label", "Table 4"), ("file", "si"), ("created", "2026-11-18")):
            self.assertTrue(first[header.index(column):].startswith(value))
        self.assertEqual(second.split(), ["2", "remark"])
        self.assertEqual(second.index("remark"), header.index("kind"))
        self.assertNotIn("canary", plain.stdout)
        compact = self.raw("list", "--json")
        self.assertEqual(compact.returncode, 0, compact.stderr)
        self.assertEqual(compact.stdout, json.dumps(list(reversed(records)), ensure_ascii=False) + "\n")

    def test_list_empty_and_text_filters(self):
        self.write("excerpts.json", '{"pdfmd-excerpts":1,"next-id":1,"sources":{},"excerpts":[]}')
        self.assertEqual(self.raw("list").stdout, "No excerpt records.\n")
        self.command("add", "--key", "glass", "--page", "24")
        self.command("add", "--key", "glass", "--page", "25")
        self.command("add", "--key", "clay", "--page", "26")
        self.write("draft.md", "See [@glass#1].")
        for options, expected in ((("--key", "glass"), ["1", "2"]), (("--unused",), ["2", "3"]),
                                  (("--key", "glass", "--unused"), ["2"])):
            with self.subTest(options=options):
                result = self.raw("list", *options)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual([row.split()[0] for row in result.stdout.splitlines()[1:]], expected)
        self.assertEqual(self.raw("list", "--key", "missing").stdout, "No excerpt records.\n")

    def test_list_fits_terminal_cells_and_keeps_one_line_per_record(self):
        from pdfmd_ansi.text import text_width
        from pdfmd_excerpts.cli import command

        self.command("add", "--key", "glass", "--page", "iv", "--label", "漢字" * 30 + "\nsecond line")
        with mock.patch("sys.stdout", new_callable=io.StringIO) as output, \
                mock.patch.object(output, "isatty", return_value=True), \
                mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((36, 24))):
            self.assertEqual(command(["list", "--in", str(self.root)]), 0)
            header, row = output.getvalue().splitlines()
        self.assertEqual(header.split(), ["id", "key", "page", "kind", "label"])
        self.assertIn("漢字", row)
        self.assertTrue(row.endswith("…"))
        self.assertLessEqual(text_width(row), 36)

    def test_list_uses_utf8_and_eighty_columns_on_a_pipe(self):
        self.command("add", "--key", "glass", "--label", "Выдуманный " * 15)
        with mock.patch.dict(os.environ, {"PYTHONIOENCODING": "cp1252", "COLUMNS": "20"}):
            result = self.raw("list")
        self.assertEqual(result.returncode, 0, result.stderr)
        _, row = result.stdout.splitlines()
        self.assertIn("Выдуманный", row)
        self.assertTrue(row.endswith("…"))
        self.assertEqual(len(row), 80)

    def test_add_show_and_delete_never_reuses_id(self):
        added = self.command("add", "--key", "glass", "--page", "24", "--text", "An invented passage.")
        self.assertEqual(added["id"], 1)
        self.assertEqual(added["markers"], ["[@x:1]", "[@glass#1]"])
        # the project folder holds the record file alone: the writers' lock lives in pdfmd's cache
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["excerpts.json"])
        self.assertEqual(self.command("show", "1")["parts"][0]["text"], "An invented passage.")
        self.command("remove", "1")
        self.assertEqual(self.command("add", "--remark", "Check this inference.")["id"], 2)

    def test_pointer_area_secondary_quotation_and_multipart_edit(self):
        self.command("add", "--key", "glass", "--page", "iv", "--label", "abstract")
        record = self.command("show", "1")
        self.assertEqual(record["parts"], [])
        self.assertEqual(record["page"], "iv")
        self.command("edit", "1", "--page", "S1-S2", "--kind", "area", "--quoting", "An earlier invented study",
                     "--note", "A synthetic observation", "--pdf-page", "3", "--box=1,2,30,40", "--box", "2,3,31,41",
                     "--text", "First invented\nfragment", "--pdf-page", "4", "--box", "5,6,35,46", "--text", "Second fragment")
        record = self.command("show", "1")
        self.assertEqual(record["kind"], "area")
        self.assertEqual(len(record["parts"]), 2)
        self.assertEqual(record["parts"][0]["text"], "First invented fragment")
        self.assertEqual(len(record["parts"][0]["boxes"]), 2)
        self.assertEqual(record["parts"][1]["pdf-page"], 4)
        self.command("add", "--key", "glass", "--page", "", "--locator", "ch. 3", "--text", "First", "--text", "Second")
        self.assertEqual(len(self.command("show", "2")["parts"]), 2)
        self.command("edit", "2", "--remark", "An inference to review")
        self.assertNotIn("key", self.command("show", "2"))

    def test_remainder_preserves_option_like_passages_and_no_pandoc_is_needed(self):
        self.command("add", "--key", "glass", "--text=--metadata=colour: blue")
        self.assertEqual(self.command("show", "1")["parts"][0]["text"], "--metadata=colour: blue")
        with mock.patch.dict(os.environ, {"PATH": ""}):
            self.command("add", "--remark", "A synthetic inference")
            self.assertEqual(len(self.command("list")), 2)

    def test_where_forms_contexts_code_collision_and_cited_removal(self):
        self.command("add", "--key", "glass", "--page", "24")
        self.command("add", "--key", "clay", "--page", "25")
        self.write("draft.md", """[@x:1] @x#1 [-@glass#1] [see @glass#1, Table 4] [@x:1; @x:2].
`@x:1` <!-- @x:1 --> $@x:1$ \\(@x:1\\) \\@x:1 https://example.invalid/@x:1

    @x:1

```text
@x:1
```

@glass:1 @fig:1 @fig:plot#1 @tbl:1 @eq:1 @sec:1 @lst:1.
""")
        self.write("parts/claim.md", "Narrative @glass#1's claim. Then @glass#1:\n")
        self.write("other/excerpts.json", '{"pdfmd-excerpts":1,"next-id":1,"sources":{},"excerpts":[]}')
        self.write("other/another.md", "[@x:1]")
        self.write(".backups/old.md", "[@x:1]")
        places = self.command("where", "1")
        self.assertEqual(len(places), 8, places)
        self.assertEqual(sorted(place["line"] for place in places), [1] * 7 + [10])
        self.assertEqual(self.command("list", "--key", "glass")[0]["id"], 1)
        self.assertEqual(self.command("list", "--unused"), [])
        self.assertIn("is cited", self.command("remove", "1", code=1)["error"])
        self.command("remove", "1", "--force")
        self.assertIn("[@x:1]", (self.root / "draft.md").read_text(encoding="utf-8"))
        self.command("add", "--key", "glass", "--page", "26")
        self.assertEqual([item["id"] for item in self.command("list", "--unused")], [3])
        # Actual bibliography keys win, preserving case.
        self.write("refs.bib", "@book{x:2, title={Synthetic source}}")
        self.assertEqual(self.command("where", "2"), [])

    def test_both_separators_and_setting_layers_write_canonical_markers(self):
        self.config = str(self.write("global.yaml", "options: {excerpt-prefix: global}\n"))
        self.command("add", "--key", "glass:part")
        self.assertEqual(self.command("add", "--key", "glass")["markers"], ["[@global:2]", "[@glass#2]"])
        self.write(".pdfmd/config.yaml", "options: {excerpt-prefix: folder}\n")
        self.assertEqual(self.command("add", "--remark", "A note")["markers"], ["[@folder:3]"])
        self.write("metadata.yaml", "pdfmd-options: {excerpt-prefix: meta}\n")
        self.assertEqual(self.command("add", "--remark", "A note")["markers"], ["[@meta:4]"])
        draft = """---
pdfmd-options: {excerpt-prefix: Ex_1-local}
---

[@Ex_1-local#1; @Ex_1-local:1; @glass:part:1; @glass:part#1; @fig:1; @x:99a].
"""
        self.write("draft.md", draft)
        self.assertEqual(self.command("add", "--in", "draft.md", "--remark", "A note")["markers"], ["[@Ex_1-local:5]"])
        places = self.command("where", "1")
        self.assertEqual([place["marker"] for place in places],
                         ["@Ex_1-local:1", "@Ex_1-local:1", "@glass:part#1", "@glass:part#1"])

    def test_invalid_prefix_names_the_setting_and_stops_before_writing(self):
        for value in ("''", "null", "false", "'two words'", "'a:b'", "'a#b'", "fig", "tbl", "eq", "sec", "lst"):
            with self.subTest(value=value):
                self.write("draft.md", f"---\npdfmd-options: {{excerpt-prefix: {value}}}\n---\n")
                error = self.command("add", "--in", "draft.md", "--key", "glass", code=1)
                self.assertIn("excerpt-prefix", error["error"])
                self.assertFalse((self.root / "excerpts.json").exists())

    def test_where_percent_comments_and_raw_blocks_keep_line_numbers(self):
        self.command("add", "--key", "glass")
        self.write("draft.md", "%% @x:1\n@x:1 %%\n@glass#1\n\\begin{verbatim}\n@x:1\n\\end{verbatim}\n<pre>@x:1</pre>\n")
        places = self.command("where", "1")
        self.assertEqual([item["line"] for item in places], [3])
        self.write("draft.md", "---\npdfmd-options:\n  flavour: obsidian\n---\n\n@x:1\n%% @x:1\n")
        self.assertEqual([item["line"] for item in self.command("where", "1")], [6])

    def test_answers_are_utf8_whatever_the_pipe_encoding(self):
        # a pipe on Windows has the ANSI code page: a passage in Cyrillic could not be written at all, and `—` came out
        # as a byte no UTF-8 reader takes (the branch CI's Windows jobs, v3.34.1)
        self.command("add", "--key", "glass", "--page", "2", "--text", "Выдуманный отрывок — invented.")
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--excerpts", "show", "1"], cwd=self.root,
                                env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1", "PYTHONIOENCODING": "cp1252"},
                                capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertIn("Выдуманный отрывок — invented.", result.stdout.decode("utf-8"))

    def test_export_and_every_action_json_and_plain_output(self):
        self.command("add", "--key", "glass", "--page", "24", "--text", "An invented fragment.", "--note", "A note.")
        self.write("draft.md", "[@glass#1]\n")
        review = self.command("export", "-o", "review.md")["markdown"]
        self.assertIn("An invented fragment.", review)
        self.assertIn("A note.", review)
        self.assertIn("draft.md:1", review)
        self.assertEqual((self.root / "review.md").read_text(encoding="utf-8"), review)
        self.assertEqual(self.raw("export").stdout, review)
        self.command("export", "-o", "excerpts.json", code=1)
        for args in (("show", "1"), ("where", "1"), ("sources",), ("edit", "1", "--note", "Revised")):
            with self.subTest(args=args):
                result = self.raw(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                json.loads(result.stdout)
        added = self.raw("add", "--remark", "Review this inference")
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertIn("2 [@x:2]", added.stdout)
        self.assertEqual(self.raw("remove", "2").returncode, 0)

    def test_usage_errors_and_malformed_file_do_not_write_or_echo_passages(self):
        for args in ((), ("missing",), ("show", "bad"), ("add",), ("add", "--remark", "CANARY", "--key", "glass")):
            self.command(*args, code=2)
        self.command("add", "--remark", "An invented note")
        before = (self.root / "excerpts.json").read_bytes()
        self.assertEqual(self.command("list", "--problems"), [])
        for args, code in ((("show", "99"), 1), (("detach", "--all"), 2),
                           (("add", "--key", "glass", "--box", "1,2,3,4"), 2),
                           (("add", "--key", "glass", "--pdf-page", "0"), 2),
                           (("add", "--key", "glass", "--pdf-page", "1", "--box", "4,3,2,1"), 1)):
            self.command(*args, code=code)
            self.assertEqual((self.root / "excerpts.json").read_bytes(), before)
        for text in ("{CANARY", '{"pdfmd-excerpts":1,"sources":{},"excerpts":[]}'):
            self.write("excerpts.json", text)
            result = self.raw("list", "--json")
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("CANARY", result.stdout + result.stderr)

    def test_future_version_is_read_only(self):
        path = self.write("excerpts.json", '{"pdfmd-excerpts":2,"next-id":1,"sources":{},"excerpts":[],"future":"kept"}\n')
        before = path.read_bytes()
        result = self.raw("list", "--json")
        self.assertEqual(result.returncode, 0)
        self.assertIn("newer record version", result.stderr)
        self.command("add", "--remark", "No write", code=1)
        self.assertEqual(path.read_bytes(), before)

    def test_force_removal_and_plain_list_need_no_document_scan(self):
        self.command("add", "--key", "glass")
        (self.root / "draft.md").write_bytes(b"\xff\xfe")
        self.assertEqual(self.command("list")[0]["id"], 1)
        self.command("remove", "1", "--force")

    def test_discovery_relative_origins_off_parent_and_verbose(self):
        self.write("nested/draft.md", "---\npdfmd-options:\n  excerpts: ../records.json\n---\n\nDraft.")
        self.command("add", "--in", "nested/draft.md", "--key", "glass")
        self.assertTrue((self.root / "records.json").is_file())
        self.write("nested/metadata.yaml", "pdfmd-options:\n  excerpts: ../from-metadata.json\n")
        self.write("nested/draft.md", "Draft.")
        self.command("add", "--in", "nested/draft.md", "--remark", "Metadata origin")
        self.assertTrue((self.root / "from-metadata.json").is_file())
        self.write("nested/.pdfmd/config.yaml", "options:\n  excerpts: ../../from-folder.json\n")
        (self.root / "nested/metadata.yaml").unlink()
        self.command("add", "--in", "nested/draft.md", "--remark", "Folder origin")
        self.assertTrue((self.root / "from-folder.json").is_file())
        self.write("nested/draft.md", "---\npdfmd-options:\n  excerpts: off\n---\nDraft.")
        self.command("list", "--in", "nested/draft.md", code=1)
        (self.root / "nested/.pdfmd/config.yaml").unlink()
        self.write("nested/draft.md", "Draft.")
        self.command("add", "--remark", "Parent record")
        self.assertEqual(self.command("list", "--in", "nested/draft.md")[0]["note"], "Parent record")
        self.write("nested/metadata/excerpts.json", (self.root / "excerpts.json").read_text(encoding="utf-8"))
        result = self.raw("list", "--in", "nested/draft.md", "--verbose", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("further file ignored", result.stderr)

    def test_two_writers_reread_under_the_lock(self):
        processes = [subprocess.Popen([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--excerpts", "add",
                                       "--key", "glass", "--json"], cwd=self.root,
                                      env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"},
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8") for _ in range(2)]
        ids = []
        for process in processes:
            out, err = process.communicate(timeout=60)
            self.assertEqual(process.returncode, 0, out + err)
            ids.append(json.loads(out)["id"])
        self.assertEqual(sorted(ids), [1, 2])
        self.assertEqual([item["id"] for item in self.command("list")], [1, 2])


class RecordFormat(unittest.TestCase):
    def test_canonical_round_trip_unknown_fields_order_unicode_and_rounding(self):
        from pdfmd_excerpts.record import canonical, validate
        data = {"pdfmd-excerpts": 1, "next-id": 4, "future": {"keep": True},
                "sources": {"zeta": {"future": "é", "file": "z.pdf", "more": {"si": {"file": "s.pdf", "future": 7}}}, "alpha": {}},
                "excerpts": [{"kind": "remark", "id": 3, "note": "A note", "future": 9},
                             {"kind": "area", "id": 1, "key": "zeta", "page": "S1", "future": [1],
                              "parts": [{"pdf-page": 2, "text": "Éclat\ntrial", "text-from": "typed", "future": "yes",
                                         "boxes": [[1.234, 2.345, 30.567, 40.678]]}]}]}
        text = canonical(validate(data))
        self.assertEqual(canonical(json.loads(text)), text)
        self.assertNotIn("\\u", text)
        self.assertTrue(text.endswith("\n"))
        self.assertNotIn("\r", text)
        self.assertLess(text.index('"alpha"'), text.index('"zeta"'))
        restored = json.loads(text)
        self.assertEqual([record["id"] for record in restored["excerpts"]], [1, 3])
        self.assertEqual(restored["excerpts"][0]["parts"][0]["future"], "yes")
        self.assertEqual(restored["excerpts"][0]["parts"][0]["boxes"][0], [1.2, 2.3, 30.6, 40.7])
        self.assertEqual(restored["sources"]["zeta"]["more"]["si"]["future"], 7)
        with tempfile.TemporaryDirectory() as folder:
            from pdfmd_excerpts.record import update, read
            path = Path(folder) / "excerpts.json"
            path.write_text(text, encoding="utf-8")
            update(path, lambda records: records["excerpts"][0].update({"label": "A table"}))
            self.assertEqual(read(path)["future"], {"keep": True})

    def test_invalid_ids_parts_maps_and_boxes(self):
        from pdfmd_excerpts.record import validate, RecordError
        base = {"pdfmd-excerpts": 1, "next-id": 2, "sources": {}, "excerpts": [{"id": 1, "kind": "text", "key": "glass", "page": "", "parts": []}]}
        invalid = []
        for ident in (0, -1, True, "1", 2):
            value = copy.deepcopy(base)
            value["excerpts"][0]["id"] = ident
            invalid.append(value)
        value = copy.deepcopy(base)
        value["excerpts"] *= 2
        invalid.append(value)
        for part in ({"pdf-page": 0}, {"boxes": [[1, 2, 3, 4]]}, {"pdf-page": 1, "boxes": [[1, 2, float("nan"), 4]]},
                     {"text-from": "guess"}, {"pdf-page": 1, "boxes": [[3, 2, 1, 4]]}):
            value = copy.deepcopy(base)
            value["excerpts"][0]["parts"] = [part]
            invalid.append(value)
        for mapping in ([[2, "41"], [1, "40"]], [[0, "1"]], [[1, 1]], "trivial"):
            value = copy.deepcopy(base)
            value["sources"] = {"glass": {"pages": mapping}}
            invalid.append(value)
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(RecordError):
                validate(value)

    def test_failed_atomic_write_preserves_original(self):
        from pdfmd_excerpts.record import update
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "excerpts.json"
            update(path, lambda data: None)
            before = path.read_bytes()
            with mock.patch.object(pdfmd, "atomic_write_text", side_effect=OSError("synthetic failure")):
                with self.assertRaises(OSError):
                    update(path, lambda data: data.update({"future": "changed"}))
            self.assertEqual(path.read_bytes(), before)

    def test_anchor_maps_cover_roman_case_and_supplement(self):
        from pdfmd_excerpts.pages import printed_page
        self.assertEqual(printed_page([[2, "41"]], 1), "")
        self.assertEqual(printed_page([[2, "41"]], 3), "42")
        self.assertEqual(printed_page([[1, "i"], [5, "1"]], 4), "iv")
        self.assertEqual(printed_page([[1, "IX"]], 2), "X")
        self.assertEqual(printed_page([[1, "S1"]], 3), "S3")
        self.assertEqual(printed_page(None, 10), "")


@unittest.skipUnless(pdfmd.pypdf, "needs optional pypdf")
class SourcePDFs(CommandFixture, unittest.TestCase):
    def pdf(self, name, words="Invented glass study", count=2, label=None, *, annotations=(), lines=(), rotations=()):
        """Small PDFs made in the test, with synthetic text and real/trivial labels."""
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
        writer = pdfmd.pypdf.PdfWriter()
        for number in range(count):
            page = writer.add_blank_page(width=200, height=200)
            if rotations:
                page.rotate(rotations[number])
                page.mediabox.lower_left = (-20, -30)
                page.mediabox.upper_right = (200, 210)
            stream = DecodedStreamObject()
            body = f"BT /F1 10 Tf 10 180 Td ({words}; printed {41 + number}) Tj"
            body += "".join(f" 0 -25 Td ({line}) Tj" for line in lines)
            stream.set_data((body + " ET").encode("ascii"))
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
            page[NameObject("/Contents")] = writer._add_object(stream)
        if label:
            writer.set_page_label(0, count - 1, style="/D", start=label)
        for number, kind, box, quad, note in annotations:
            from pypdf.generic import ArrayObject, FloatObject, TextStringObject
            annotation = DictionaryObject({
                NameObject("/Subtype"): NameObject("/" + kind),
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Rect"): ArrayObject([FloatObject(value) for value in box]),
                NameObject("/Contents"): TextStringObject(note),
            })
            if quad:
                annotation[NameObject("/QuadPoints")] = ArrayObject([FloatObject(value) for value in quad])
            writer.add_annotation(number, annotation)
        for page in writer.pages:
            if "/Annots" in page:
                page[NameObject("/Annots")] = writer._add_object(page["/Annots"])
        path = self.root / name
        with path.open("wb") as handle:
            writer.write(handle)
        return path

    @unittest.skipUnless(POPPLER_PDFTOTEXT, "needs Poppler pdftotext")
    def test_import_pdf_annotations_previews_page_map_text_notes_and_repeats(self):
        kinds = ("Highlight", "Underline", "StrikeOut", "Squiggly", "Square", "FreeText")
        annotations = []
        for index, kind in enumerate(kinds):
            y = 180 - 25 * index
            right = (55, 64, 60, 55, 55, 55)[index]
            bounds = (8, y - 3, right, y + 9)
            quad = (8, y + 9, right, y + 9, 8, y - 3, right, y - 3) if index < 4 else ()
            # The text annotation's Rect is deliberately wider than its QuadPoints.
            rect = (8, y - 3, 190, y + 9) if quad else bounds
            annotations.append((int(index != 4), kind, rect, quad, f"Note {kind}"))
        annotations.append((1, "Text", (5, 6, 7, 8), (), "Unrelated note"))
        path = self.pdf("marked.pdf", words="Amber glass outside", annotations=annotations,
                        lines=("Blue shards outside", "Copper slag outside", "Drift sand outside"))
        operation = ("import", path.name, "--key", "glass")
        missing = self.command(*operation, code=1)
        self.assertIn("sources add", missing["error"])
        self.command("sources", "add", "glass", path.name, "--pages", '[[2,"41"]]')
        before, original_pdf = (self.root / "excerpts.json").read_bytes(), path.read_bytes()
        preview = self.command(*operation, "--dry-run")
        self.assertEqual((self.root / "excerpts.json").read_bytes(), before)
        self.assertEqual(self.command(*operation), preview)
        self.assertEqual(self.command(*operation), [])
        items = {item["note"]: item for item in self.command("list")}
        self.assertEqual(len(items), 6)
        for index, (kind, words) in enumerate(zip(kinds, ("Amber gla", "Blue shards", "Copper slag", "Drift sand"))):
            record = items[f"Note {kind}"]
            y = 180 - 25 * index
            self.assertEqual((record["kind"], record["page"]), ("text", "41"))
            self.assertEqual(record["parts"], [{"pdf-page": 2, "boxes": [[8, y - 3, annotations[index][3][2], y + 9]],
                                               "text": words, "text-from": "pdf"}])
        self.assertEqual(items["Note Square"]["parts"], [{"pdf-page": 1, "boxes": [[8, 77, 55, 89]]}])
        self.assertEqual(items["Note Square"]["page"], "")
        self.assertEqual(items["Note FreeText"]["kind"], "area")
        self.assertEqual(path.read_bytes(), original_pdf)

    def test_import_area_on_a_registered_supplement_needs_no_poppler(self):
        from pdfmd_excerpts.import_pdf import import_annotations

        primary = self.pdf("primary.pdf")
        extra = self.pdf("extra.pdf", annotations=[(1, "Square", (10, 20, 30, 40), (), "An area")])
        self.command("sources", "add", "glass", primary.name)
        missing = self.command("import", extra.name, "--key", "glass", code=1)
        self.assertIn("sources add", missing["error"])
        path = self.root / "excerpts.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        records["sources"]["glass"]["more"] = {"si": {"file": extra.name, "pages": [[1, "S1"]]}}
        path.write_text(json.dumps(records), encoding="utf-8")
        with mock.patch.object(pdfmd, "which", return_value=None):
            (area,), not_imported = import_annotations(path, extra, "glass")
        self.assertEqual(not_imported, [])
        self.assertEqual((area["file"], area["page"], area["note"]), ("si", "S2", "An area"))
        self.assertEqual(area["parts"], [{"pdf-page": 2, "boxes": [[10, 20, 30, 40]]}])

    @unittest.skipUnless(POPPLER_PDFTOTEXT, "needs Poppler pdftotext")
    def test_import_combines_quads_in_default_space_on_rotated_pages(self):
        first_line = (8, 189, 66, 189, 8, 177, 66, 177)
        second_line = (8, 164, 64, 164, 8, 152, 64, 152)
        path = self.pdf("rotated.pdf", count=4, words="Amber glass outside", label=20,
                        annotations=[(page, "Highlight", (8, 152, 66, 189), first_line + second_line, "")
                                     for page in range(4)],
                        lines=("Blue shards outside",), rotations=(0, 90, 180, 270))
        self.command("sources", "add", "glass", path.name, "--pages", "labels")
        records = self.command("import", path.name, "--key", "glass")
        self.assertEqual([item["page"] for item in records], ["20", "21", "22", "23"])
        for number, item in enumerate(records, 1):
            with self.subTest(number=number):
                self.assertEqual(item["parts"], [{"pdf-page": number, "boxes": [[8, 177, 66, 189], [8, 152, 64, 164]],
                                                  "text": "Amber glass Blue shards", "text-from": "pdf"}])

    @unittest.skipUnless(sys.platform == "darwin" and POPPLER_PDFTOTEXT, "needs macOS xattr and Poppler pdftotext")
    def test_import_reads_a_compressed_fragmented_skim_archive(self):
        import bz2
        import plistlib

        path = self.pdf("skim.pdf", words="Amber glass outside")
        self.command("sources", "add", "glass", path.name, "--pages", '[[2,"41"]]')
        fields = {"type": "Highlight", "pageIndex": 1, "bounds": "{{8, 177}, {58, 12}}",
                  "quadrilateralPoints": ["{0, 12}", "{58, 12}", "{0, 0}", "{58, 0}"], "contents": "A Skim note"}
        uid = plistlib.UID
        keys = list(fields)
        values = list(fields.values())
        points = values[3]
        values[3] = {"NS.objects": [uid(13 + i) for i in range(len(points))], "$class": uid(17)}
        archive = {"$archiver": "NSKeyedArchiver", "$version": 100000, "$top": {"root": uid(1)}, "$objects": [
            "$null", {"NS.objects": [uid(2)], "$class": uid(17)},
            {"NS.keys": [uid(3 + i) for i in range(len(keys))],
             "NS.objects": [uid(8 + i) for i in range(len(values))], "$class": uid(18)},
            *keys, *values, *points, {"$classname": "NSMutableArray"}, {"$classname": "NSMutableDictionary"},
        ]}
        compressed = bz2.compress(plistlib.dumps(archive, fmt=plistlib.FMT_BINARY))
        stem = "net_sourceforge_skim-app"
        suffix = "#S"
        fragment = stem + "_6EE08252-84CC-47AC-ADAB-2830CC72F95F"
        wrapper = plistlib.dumps({stem + "_has_wrapper": True, stem + "_unique_key": fragment,
                                  stem + "_number_of_fragments": 2}, fmt=plistlib.FMT_BINARY)
        for name, data in ((stem + "_notes", wrapper), (fragment + "-0", compressed[:100]),
                           (fragment + "-1", compressed[100:])):
            subprocess.run(["/usr/bin/xattr", "-wx", name + suffix, data.hex(), str(path)],
                           check=True, capture_output=True)
        [record] = self.command("import", path.name, "--key", "glass")
        self.assertEqual((record["kind"], record["page"], record["note"]), ("text", "41", "A Skim note"))
        self.assertEqual(record["parts"], [{"pdf-page": 2, "boxes": [[8, 177, 66, 189]],
                                           "text": "Amber glass", "text-from": "pdf"}])
        self.assertEqual(self.command("import", path.name, "--key", "glass"), [])

    @unittest.skipUnless(sys.platform == "darwin", "needs macOS xattr")
    def test_import_lists_skim_text_notes_without_creating_records(self):
        import plistlib

        path = self.pdf("skim.pdf")
        self.command("sources", "add", "glass", path.name, "--pages", '[[2,"41"]]')
        record_path = self.root / "excerpts.json"
        before = record_path.read_bytes()
        operation = ("import", path.name, "--key", "glass")
        stem = "net_sourceforge_skim-app"
        archive = stem + "_notes#S"
        text = ("* Highlight, page 1\n\nAmber glass\n\nA separate paragraph \n\n"
                "* FreeText, page 2\n\nBlue clay — café \n\n")
        entries = [{"heading": "* Highlight, page 1", "text": "Amber glass\n\nA separate paragraph",
                    "status": "not imported: no position"},
                   {"heading": "* FreeText, page 2", "text": "Blue clay — café",
                    "status": "not imported: no position"}]

        def attribute(name, data):
            subprocess.run(["/usr/bin/xattr", "-wx", name, data.hex(), str(path)], check=True, capture_output=True)

        attribute(stem + "_text_notes#S", plistlib.dumps(text, fmt=plistlib.FMT_BINARY))
        for options in ((), ("--dry-run",)):
            with self.subTest(options=options):
                done = self.raw(*operation, *options)
                self.assertEqual(done.returncode, 0, done.stderr)
                for entry in entries:
                    self.assertIn(entry["heading"], done.stdout)
                    self.assertIn(entry["text"], done.stdout)
                self.assertEqual(done.stdout.count("not imported: no position"), len(entries))
                self.assertEqual(self.command(*operation, *options), {"records": [], "not-imported": entries})
                self.assertEqual(record_path.read_bytes(), before)

        attribute(archive, b"unreadable archive")
        self.assertEqual(self.command(*operation), {"records": [], "not-imported": entries})
        self.assertEqual(record_path.read_bytes(), before)
        attribute(archive, plistlib.dumps([
            {"type": "Square", "pageIndex": 1, "bounds": "{{10, 20}, {20, 20}}", "contents": "An archived area"}
        ], fmt=plistlib.FMT_BINARY))
        [record] = self.command(*operation)
        self.assertEqual((record["id"], record["page"], record["note"]), (1, "41", "An archived area"))
        self.assertEqual(record["parts"], [{"pdf-page": 2, "boxes": [[10, 20, 30, 40]]}])
        self.assertEqual(self.command(*operation), [])

    @unittest.skipUnless(sys.platform == "darwin", "needs macOS xattr")
    def test_import_lists_raw_skim_text_notes_beside_pdf_annotations(self):
        path = self.pdf("marked.pdf", annotations=[(0, "Square", (10, 20, 30, 40), (), "A saved area")])
        self.command("sources", "add", "glass", path.name)
        text = "* Note, page 1\n\nAn unplaced note\n"
        subprocess.run(["/usr/bin/xattr", "-wx", "net_sourceforge_skim-app_text_notes",
                        text.encode("utf-8").hex(), str(path)], check=True, capture_output=True)
        answer = self.command("import", path.name, "--key", "glass")
        [record] = answer["records"]
        self.assertEqual((record["id"], record["note"]), (1, "A saved area"))
        self.assertEqual(answer["not-imported"], [{"heading": "* Note, page 1", "text": "An unplaced note",
                                                   "status": "not imported: no position"}])
        self.assertEqual(self.command("list"), [record])

    def test_source_identity_hash_state_labels_and_map_fill_only_on_add(self):
        path = self.pdf("glass.pdf")
        before = path.read_bytes()
        self.command("sources", "add", "glass", "glass.pdf", "--pages", '[[2,"41"]]')
        self.assertEqual(self.command("sources")[0]["state"], "ok")
        self.command("add", "--key", "glass", "--pdf-page", "3")
        self.assertEqual(self.command("show", "1")["page"], "42")
        self.command("edit", "1", "--pdf-page", "1")
        self.assertEqual(self.command("show", "1")["page"], "42")
        self.command("add", "--key", "glass", "--pdf-page", "2", "--page", "typed")
        self.assertEqual(self.command("show", "2")["page"], "typed")
        self.command("sources", "add", "glass", "glass.pdf", "--pages", "labels", code=1)
        self.assertEqual(path.read_bytes(), before)
        labelled = self.pdf("clay.pdf", label=81)
        self.command("sources", "add", "clay", "clay.pdf", "--pages", "labels")
        self.command("add", "--key", "clay", "--pdf-page", "2")
        self.assertEqual(self.command("show", "3")["page"], "82")
        self.command("export", "-o", "clay.pdf", code=1)
        labelled.write_bytes(labelled.read_bytes() + b"\n% changed\n")
        states = {item["key"]: item["state"] for item in self.command("sources")}
        self.assertEqual(states["clay"], "changed")
        labelled.unlink()
        self.assertEqual(self.command("sources")[0]["state"], "missing")

    @unittest.skipUnless(POPPLER_PDFTOTEXT, "needs Poppler pdftotext")
    def test_check_and_reanchor_after_a_cover_page_is_added(self):
        source = self.pdf("glass.pdf", count=1)
        self.pdf("missing.pdf", count=1)
        self.command("sources", "add", "glass", "glass.pdf")
        self.command("sources", "add", "missing", "missing.pdf")
        (self.root / "missing.pdf").unlink()
        self.write("draft.md", "[@x:1].\n")
        self.write("refs.bib", "@book{glass, title={Invented glass}}")
        self.command("add", "--key", "glass", "--pdf-page", "1", "--text", "Inventedglass study",
                     "--box", "10,170,103,190", "--page", "41")
        self.command("add", "--key", "glass", "--kind", "area", "--pdf-page", "1", "--box", "20,40,80,90")
        self.command("add", "--key", "glass", "--pdf-page", "1", "--text", "printed 41", "--box", "199,5,210,15")
        self.assertEqual({item["code"] for item in self.command("check", code=1)},
                         {"excerpt-source-missing", "excerpt-box", "excerpt-unused"})
        writer = pdfmd.pypdf.PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.append(source)
        with source.open("wb") as handle:
            writer.write(handle)
        before = source.read_bytes()
        self.assertIn("excerpt-source-changed", {item["code"] for item in self.command("check", code=1)})
        [updated] = self.command("reanchor", "glass")
        self.assertEqual(updated["state"], "updated")
        original = self.command("show", "1")
        self.assertEqual(original["page"], "41")
        self.assertEqual(original["parts"][0]["pdf-page"], 2)
        self.assertNotEqual(original["parts"][0]["boxes"], [[10, 170, 103, 190]])
        self.assertEqual(self.command("show", "2")["parts"][0]["boxes"], [[20, 40, 80, 90]])
        self.assertEqual(self.command("show", "2")["parts"][0]["pdf-page"], 2)
        self.assertEqual(source.read_bytes(), before)
        final = self.command("check")
        self.assertEqual({item["code"] for item in final}, {"excerpt-source-missing", "excerpt-unused"})

    @unittest.skipUnless(POPPLER_PDFTOTEXT, "needs Poppler pdftotext")
    def test_reanchor_lists_unresolved_parts_without_committing_a_source(self):
        source = self.pdf("glass.pdf", count=1)
        self.command("sources", "add", "glass", "glass.pdf")
        self.command("add", "--key", "glass", "--pdf-page", "1", "--text", "Invented glass")
        self.command("add", "--key", "glass", "--pdf-page", "1", "--text", "Unavailable passage")
        record = self.root / "excerpts.json"
        before = record.read_bytes()
        source.write_bytes(source.read_bytes() + b"\n% changed\n")
        [review] = self.command("reanchor", "glass", code=1)
        self.assertEqual(review["state"], "review")
        self.assertEqual([item["id"] for item in review["located"]], [1])
        self.assertEqual([item["id"] for item in review["unresolved"]], [2])
        self.assertEqual(record.read_bytes(), before)


    def test_sources_match_file_doi_title_name_cover_and_likeness(self):
        self.pdf("known.pdf", "Synthetic file identity", count=3)
        self.pdf("renamed.pdf", "Synthetic DOI 10.1234/invented", count=2)
        self.pdf("untitled.pdf", "Imaginary River Stones", count=2)
        self.pdf("named.pdf", "Synthetic filename identity", count=2)
        self.write("refs.json", json.dumps([
            {"id": "filekey", "file": "known.pdf", "page": "41-42", "pages": "41-42"},
            {"id": "doikey", "DOI": "10.1234/invented"},
            {"id": "titlekey", "title": "Imaginary River Stones"}, {"id": "named"}]))
        self.write("metadata.yaml", "bibliography: refs.json\n")
        proposals = self.command("sources", "match")
        reasons = {item["key"]: item["candidates"][0]["reason"] for item in proposals}
        self.assertEqual(reasons, {"filekey": "file", "doikey": "doi", "titlekey": "title", "named": "name"})
        self.assertEqual(next(item for item in proposals if item["key"] == "filekey")["candidates"][0]["pages"], [[2, "41"]])
        self.command("sources", "match", "--apply")
        self.assertEqual(len(self.command("sources")), 4)
        self.write("refs.bib", "@book{nmed, title={Unmatched invented title}, pages={41--42}}\n")
        self.write("metadata.yaml", "bibliography: refs.bib\n")
        proposals = self.command("sources", "match")
        fuzzy = next(item for item in proposals if item["key"] == "nmed")
        self.assertEqual(fuzzy["candidates"][0]["reason"], "likeness")
        self.assertFalse(fuzzy["apply"])
        before = (self.root / "excerpts.json").read_bytes()
        self.command("sources", "match", "--apply", code=1)
        self.assertEqual((self.root / "excerpts.json").read_bytes(), before)

    def test_supplement_maps_and_unknown_fields_survive_cli_edit(self):
        self.pdf("glass.pdf")
        self.pdf("si.pdf")
        self.command("sources", "add", "glass", "glass.pdf")
        path = self.root / "excerpts.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["future"] = {"keep": True}
        data["sources"]["glass"]["more"] = {"si": {"file": "si.pdf", "pages": [[1, "S1"]], "future": 9}}
        path.write_text(json.dumps(data), encoding="utf-8")
        self.command("add", "--key", "glass", "--file", "si", "--pdf-page", "2")
        self.assertEqual(self.command("show", "1")["page"], "S2")
        self.command("edit", "1", "--note", "Synthetic note")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["future"], {"keep": True})
        self.assertEqual(data["sources"]["glass"]["more"]["si"]["future"], 9)

    def test_conflicting_source_matches_are_proposals_without_writes(self):
        self.pdf("first.pdf", "Synthetic DOI 10.1234/invented")
        self.pdf("second.pdf", "Synthetic DOI 10.1234/invented")
        self.write("refs.bib", "@book{glass, doi={10.1234/invented}}")
        proposals = self.command("sources", "match")
        self.assertEqual(len(proposals[0]["candidates"]), 2)
        self.assertFalse(proposals[0]["apply"])
        self.command("sources", "match", "--apply", code=1)
        self.assertFalse((self.root / "excerpts.json").exists())


CASES = json.loads((ROOT / "tests" / "fixtures" / "excerpts-cases.json").read_text(encoding="utf-8"))


class ResolverFixture(CommandFixture):
    def setUp(self):
        super().setUp()
        records = [
            {"id": 1, "key": "glass", "page": "41"},
            {"id": 2, "key": "glass", "page": "42"},
            {"id": 3, "key": "glass", "page": "45"},
            {"id": 4, "kind": "remark"},
            {"id": 5, "key": "glass", "page": "43", "locator": "ch. 3"},
            {"id": 6, "key": "glass", "page": ""},
            {"id": 7, "key": "clay", "page": "9-10"},
            {"id": 8, "key": "glass", "page": "xi"},
            {"id": 9, "key": "glass", "page": "ix"},
            {"id": 10, "key": "glass", "page": "x"},
            {"id": 11, "key": "clay", "page": "S10"},
            {"id": 12, "key": "clay", "page": "S9"},
        ]
        for item in records:
            item.setdefault("kind", "text")
            item.update(note="CANARY_EXCERPT_NOTE", quoting="CANARY_EXCERPT_QUOTING", parts=[
                {"pdf-page": 1, "boxes": [[223.1, 224.2, 225.3, 226.4]], "text": "CANARY_EXCERPT_TEXT",
                 "text-from": "typed"}])
        self.write("excerpts.json", json.dumps({"pdfmd-excerpts": 1, "next-id": 13, "excerpts": records, "sources": {}}))
        self.write("refs.bib", """@book{glass, author={Tester, Pat}, title={Invented Glass}, year={2001}}
@book{clay, author={Tester, Jo}, title={Invented Clay}, year={2002}}
@book{unused, author={Tester, Lee}, title={Invented Unused}, year={2003}}
""")

    def build(self, *words, env=None, code=0):
        command = [sys.executable, str(ROOT / "scripts" / "pdfmd"), *words]
        result = subprocess.run(command, cwd=self.root, env={**os.environ, "PDFMD_CONFIG": self.config,
                                                            "PDFMD_NO_PROMPT": "1", **(env or {})},
                                capture_output=True, encoding="utf-8", timeout=120)
        if code is not None:
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn("CANARY_EXCERPT", result.stdout + result.stderr)
        return result


class TextResolver(ResolverFixture, unittest.TestCase):
    def test_lint_checks_excerpt_markers_quotes_and_overlap(self):
        record = self.root / "excerpts.json"
        data = json.loads(record.read_bytes())
        data["excerpts"][0]["parts"] = [{"text": "The glue-\nprintedinvented phrase and ﬁnal words. One two three four five six.",
                                        "text-from": "pdf"}]
        data["excerpts"][1]["parts"] = [{"text": "A wholly alternate excerpt", "text-from": "typed"}]
        data["excerpts"][2]["parts"] = [{"text": "Optical reading", "text-from": "ocr"}]
        data["excerpts"].append({"id": 13, "key": "gone", "page": "7", "kind": "text", "parts": []})
        data["next-id"] = 14
        record.write_text(json.dumps(data), encoding="utf-8")
        self.write("draft.md", """---
bibliography: refs.bib
---

"The glueprinted [editorial] invented [...] final words" [@x:1, p. 41, Table 4].

“A wholly alternate excerpt” [@x:1].

"That is invented differently" [@x:3].

"This is unrelated prose" [@x:1].

One two three four five six [@x:1, 98].

[@x:99]. [@clay#1]. [@x:13]. And @x:4.
""")
        answer = self.build("--check", "draft.md", code=1).stdout
        for code in ("excerpt-unknown", "excerpt-key-mismatch", "excerpt-bib", "excerpt-locator-differs",
                     "excerpt-remark-narrative", "excerpt-overlap"):
            self.assertEqual(answer.count(f"[{code}]"), 1, answer)
        self.assertEqual(answer.count("[excerpt-quote]"), 3, answer)
        self.assertIn("note: quotation matches uncited excerpt 2", answer)
        self.assertIn("note: quotation is absent", answer)
        self.assertIn("warning: quotation is absent", answer)
        self.assertIn("6 words as in excerpt 1", answer)
        self.assertNotIn("[cite-missing]", answer)
        record.write_text(json.dumps({key: value for key, value in data.items() if key != "next-id"}), encoding="utf-8")
        self.assertIn("missing or invalid next-id  [excerpt-file]", self.build("--check", "draft.md", code=1).stdout)

    def test_lint_excerpt_thresholds_and_ignore(self):
        self.write("refs.bib", "@book{glass, title={Invented Glass}}\n")
        self.command("edit", "1", "--text", "One two three four five six")
        self.write("draft.md", """---
bibliography: refs.bib
pdfmd-options: {excerpt-quote-min-words: 4, excerpt-overlap-words: 0}
---

"Three invented words" and one two three four five six [@x:1].

<!-- pdfmd-check: ignore excerpt-unknown -->
[@x:99].
""")
        self.assertIn("no problems", self.build("--check", "draft.md", "--strict").stdout)

    def test_external_metadata_markers_are_checked_and_count_as_used(self):
        self.write("draft.md", "An invented claim.\n")
        self.write("metadata.yaml", "nocite: '[@x:1; @x:99; @clay#2]'\n")
        output = self.build("--check", "draft.md", code=1).stdout
        self.assertIn("metadata.yaml:1: error", output)
        self.assertIn("[excerpt-unknown]", output)
        self.assertIn("[excerpt-key-mismatch]", output)
        issues = self.command("check", code=1)
        self.assertFalse(any(item["message"] == "excerpt 1 is unused" for item in issues))
        self.assertEqual([item["id"] for item in self.command("list", "--problems")], [2])

    def test_repeat_page_detaches_to_literal_locator(self):
        path = self.write("draft.md", """---
pdfmd-options: {excerpt-repeat: page, pagecite: auto}
---

First [@glass, p. 41]. Next [@x:2, Table 4]. Again [@x#3].

Separate [@x:2].
""")
        self.command("detach", "--all", "draft.md")
        self.assertIn("First [@glass, p. 41]. Next (42, Table 4). Again (45).",
                      path.read_text(encoding="utf-8"))
        self.assertIn("Separate [@glass, p. 42].", path.read_text(encoding="utf-8"))

    def test_shared_detach_cases(self):
        from pdfmd_excerpts.detach import text_for
        for source, expected in CASES:
            with self.subTest(source=source):
                path = self.write("draft.md", source)
                self.assertEqual(text_for(path, [], source, diagnostics=False), expected)

    def test_detach_selection_remove_and_preserve_crlf(self):
        path = self.write("draft.md", "ignored")
        path.write_bytes(b"One [@x:1]. Two [@glass:2].\r\n")
        answer = self.command("detach", "2", "draft.md")
        self.assertEqual(answer[0]["markers"], 1)
        self.assertEqual(path.read_bytes(), b"One [@x:1]. Two [@glass, p. 42].\r\n")
        self.command("remove", "1", "--detach")
        self.assertEqual(path.read_bytes(), b"One [@glass, p. 41]. Two [@glass, p. 42].\r\n")
        self.assertEqual(self.command("detach", "--all", "draft.md"), [])

    def test_check_uses_resolved_keys(self):
        self.write("draft.md", "---\nbibliography: refs.bib\n---\n\n[@x:1] [@x:7] [@x:4].\n")
        answer = self.build("--check", "draft.md")
        self.assertNotIn("cite-missing", answer.stdout + answer.stderr)
        self.assertIn("bibliography keys never cited: @unused  [citation-unused]", answer.stdout)
        self.write("refs.bib", "@book{glass, title={Invented Glass}}")
        answer = self.build("--check", "draft.md", code=None)
        self.assertIn("@clay is not in the bibliography", answer.stdout + answer.stderr)
        self.assertNotIn("@x:7 is not in the bibliography", answer.stdout + answer.stderr)


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class PandocResolver(ResolverFixture, unittest.TestCase):
    def test_repeat_page_uses_the_csl_mode_and_preserves_the_default(self):
        from test_pagecite import csl

        for kind in ("author-date", "note", "numeric"):
            with self.subTest(kind=kind):
                self.write("style.csl", csl(kind))
                outputs = {}
                for repeat in ("", ", excerpt-repeat: full", ", excerpt-repeat: page"):
                    self.write("draft.md", f"""---
bibliography: refs.bib
csl: style.csl
pdfmd-options: {{pagecite: auto{repeat}}}
---

First [@x:1]. Next [@glass#2, Table 4]. Again [@x#3].

Separate [@x:2].
""")
                    self.build("draft.md", "--to", "plain", "-o", "out.txt", "--no-stamp", "--no-backup")
                    outputs[repeat] = (self.root / "out.txt").read_bytes()
                self.assertEqual(outputs[""], outputs[", excerpt-repeat: full"])
                actual = outputs[", excerpt-repeat: page"]
                if kind == "author-date":
                    self.assertIn(b"Next (42, Table 4). Again (45).", actual)
                    self.assertIn(b"Separate (Tester, p. 42).", actual)
                else:
                    self.assertEqual(actual, outputs[""])

    def test_shared_pandoc_cases(self):
        import re
        for source, expected in CASES:
            with self.subTest(source=source):
                results = []
                for text in (source, expected):
                    self.write("draft.md", text + "\n")
                    self.build("draft.md", "--to", "html", "--standalone", "-o", "out.html",
                               "--no-stamp", "--no-backup", "--no-cache")
                    output = (self.root / "out.html").read_text(encoding="utf-8")
                    results.append(re.sub(r"\s+", " ", output))
                self.assertEqual(*results)

    def test_real_key_wins_only_warns_on_an_actual_clash_and_strict_fails(self):
        self.write("refs.bib", """@book{x:1, author={Real, Ada}, title={The Real Source}, year={2019}}
@book{glass, author={Tester, Pat}, title={Invented Glass}, year={2001}}
@book{smith:2019, author={Smith, Ada}, title={Ordinary}, year={2019}}
""")
        self.write("draft.md", "[@x:1; @x#1; @smith:2019]. Then [@other#1; @x:99; @x:7].\n")
        result = self.build("draft.md", "--to", "html", "-o", "out.html", "--strict", "--no-backup", "--no-stamp", code=1)
        output = (self.root / "out.html").read_text(encoding="utf-8")
        self.assertIn('data-cites="x:1 glass smith:2019"', output)
        said = result.stdout + result.stderr
        self.assertIn("write @glass#1 for the excerpt", said)
        self.assertNotIn("bibliography has a key 'smith:2019'", said)
        self.assertIn("@other#1: excerpt 1 belongs to glass", said)
        self.assertIn("excerpt 99 is not in excerpts.json", said)
        self.assertIn("excerpt 7: its key clay is not in the bibliography", said)

    def test_locators_biblatex_and_markup_switches(self):
        self.write("draft.md", """---
pdfmd-options:
  excerpt-prefix: src
  excerpt-page-terms: [S., Ss.]
  pagecite-terms: [Bl., Bll.]
bibliography: refs.bib
---

[@src#1; @glass:2]. [@src:1, Bl. 8].
""")
        self.build("draft.md", "--to", "latex", "--biblatex", "-o", "out.tex", "--no-stamp", "--no-backup")
        output = (self.root / "out.tex").read_text(encoding="utf-8")
        self.assertIn(r"{glass}", output)
        self.assertRegex(output, r"Ss\. 41")
        self.assertIn("Bl. 8", output)
        for option in (("--no-auto", "excerpts"), ("--no-markup",), ("--from", "markdown"), ("--flavour", "pandoc")):
            self.build("draft.md", "--to", "html", "-o", "out.html", "--no-stamp", "--no-backup", *option)
            self.assertIn("src:1", (self.root / "out.html").read_text(encoding="utf-8"))

    def test_missing_and_invalid_record_are_visible_and_deduplicated(self):
        self.write("draft.md", "[@x:1; @x:2] and @x:1.\n")
        record = self.root / "excerpts.json"
        record.unlink()
        args = ("draft.md", "--to", "html", "-o", "out.html", "--no-stamp", "--no-backup")
        result = self.build(*args)
        self.assertEqual((result.stdout + result.stderr).count("3 excerpt markers but no excerpts.json"), 1)
        record.write_text("{CANARY_EXCERPT", encoding="utf-8")
        result = self.build(*args)
        self.assertIn("excerpts.json: invalid JSON", result.stdout + result.stderr)

    def test_live_preview_for_unsaved_text(self):
        text = "A [@x:1;\n@x:2].\n\n## Next section\n"
        result = self.build("--api", "POST", "/api/render", json.dumps({"path": "draft.md", "text": text}))
        preview = json.loads(result.stdout)["html"]
        self.assertIn("@glass, pp. 41–42", preview)
        self.assertNotIn("@x:1", preview)
        self.assertIn('data-pos="draft.md@4:1-5:1"', preview)

    def test_merged_locator_and_pagecite_use_the_resolved_source(self):
        self.write("author-date.csl", """<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text">
<info><title>Synthetic Author Date</title><id>urn:uuid:00000000-0000-4000-8000-000000000002</id>
<category citation-format="author-date"/></info>
<citation><layout prefix="(" suffix=")" delimiter="; ">
<group delimiter=", "><names variable="author"><name form="short"/></names>
<date variable="issued"><date-part name="year"/></date>
<group delimiter=" "><label variable="locator" form="short"/><text variable="locator"/></group></group>
</layout></citation></style>
""")
        self.write("draft.md", """---
bibliography: refs.bib
csl: author-date.csl
pdfmd-options: {pagecite: style}
---

[@x:3; @x:1; @x:2; @x#1]. Next [p. 60].
""")
        self.build("draft.md", "--to", "html", "-o", "out.html", "--no-stamp", "--no-backup")
        output = " ".join((self.root / "out.html").read_text(encoding="utf-8").split())
        self.assertIn("(Tester, 2001, pp. 41–42, 45)", output)
        self.assertIn("(Tester, 2001, p. 60)", output)

    def test_hyphen_initial_prefix_is_read_in_both_forms(self):
        self.write("draft.md", """---
pdfmd-options: {excerpt-prefix: -src}
bibliography: refs.bib
---

[@-src:1]. [@-src#2].
""")
        self.build("draft.md", "--to", "html", "-o", "out.html", "--no-stamp", "--no-backup")
        output = " ".join((self.root / "out.html").read_text(encoding="utf-8").split())
        self.assertIn("(Tester 2001, 41)", output)
        self.assertIn("(Tester 2001, 42)", output)


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class BuildIsolation(CommandFixture, unittest.TestCase):
    def test_build_resolves_the_record_instead_of_the_marker(self):
        self.command("add", "--key", "glass", "--page", "41")
        self.write("refs.bib", "@book{glass, title={Invented glass}, author={Test, Pat}, year={2001}}\n")
        self.write("draft.md", "An invented claim [@x:1].\n")
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "draft.md",
                                 "--to", "html", "-o", "out.html", "--no-stamp", "--no-backup"],
                                cwd=self.root, capture_output=True, encoding="utf-8", timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = (self.root / "out.html").read_text(encoding="utf-8")
        self.assertIn('data-cites="glass"', output)
        self.assertRegex(output, r"Test\s+2001[,\s]+41")

    def test_record_presence_has_no_build_effect_without_markers(self):
        self.write("draft.md", "---\ntitle: Synthetic trial\nidentifier: urn:uuid:00000000-0000-4000-8000-000000000001\n---\n\nAn invented claim.\n")
        for writer in ("html", "latex", "typst", "docx", "epub", "gfm"):
            command = [sys.executable, str(ROOT / "scripts" / "pdfmd"), "draft.md", "--to", writer, "-o", "out." + writer,
                       "--no-backup", "--no-stamp", "--no-cache", "--no-auto", "bib", "crossref"]
            env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1", "SOURCE_DATE_EPOCH": "1700000000"}
            first = subprocess.run(command, cwd=self.root, env=env, capture_output=True, encoding="utf-8", timeout=120)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            before = (self.root / ("out." + writer)).read_bytes()
            self.command("add", "--key", "glass", "--page", "41", "--text", "CANARY_INVENTED_PASSAGE", "--note", "CANARY_INVENTED_NOTE")
            second = subprocess.run(command, cwd=self.root, env=env, capture_output=True, encoding="utf-8", timeout=120)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual((self.root / ("out." + writer)).read_bytes(), before, writer)
            self.assertNotIn("CANARY_INVENTED", second.stdout + second.stderr)
            (self.root / "excerpts.json").unlink()


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class CanaryBuilds(ResolverFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.record = self.root / "excerpts.json"
        self.cache = self.root / "cache"
        self.env = {"XDG_CACHE_HOME": str(self.cache), "LOCALAPPDATA": str(self.cache),
                    "SOURCE_DATE_EPOCH": "1700000000"}
        self.write("draft.md", """---
title: Invented Canary Trial
identifier: urn:uuid:00000000-0000-4000-8000-000000000001
bibliography: refs.bib
---

Citation [@x:1]. Next [@glass:2].
""")
        self.flags = ("--no-stamp", "--no-backup", "--build-log", "on", "--verbose")

    def run_build(self, *args):
        return self.build(*args, *self.flags, env=self.env)

    def scan(self, name, data):
        import zipfile

        self.assertNotIn(b"CANARY_EXCERPT", data, name)
        self.assertNotIn(b"223.1, 224.2, 225.3, 226.4", data, name)
        if zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for member in archive.namelist():
                    self.scan(f"{name}/{member}", archive.read(member))
            return
        if not data.startswith(b"%PDF-"):
            return
        try:
            from pypdf import PdfReader
            from pypdf.generic import DictionaryObject, IndirectObject, StreamObject
        except ImportError:
            self.skipTest("needs pypdf to inspect PDF streams and attachments")
        reader = PdfReader(io.BytesIO(data))
        for page in reader.pages:
            self.scan(f"{name}/text", page.extract_text().encode("utf-8"))
        for member, copies in reader.attachments.items():
            for payload in copies:
                self.scan(f"{name}/{member}", payload)
        visited = set()

        def inspect(value):
            if isinstance(value, IndirectObject):
                identity = (value.idnum, value.generation)
                if identity in visited:
                    return
                visited.add(identity)
                inspect(value.get_object())
                return
            if isinstance(value, StreamObject):
                try:
                    payload = value.get_data()
                except NotImplementedError:   # some image encodings are unsupported by pypdf
                    payload = value._data
                self.assertNotIn(b"CANARY_EXCERPT", payload, name)
            if isinstance(value, DictionaryObject):
                for item in value.values():
                    inspect(item)
            elif isinstance(value, list):
                for item in value:
                    inspect(item)
            elif isinstance(value, (str, bytes)):
                self.assertNotIn(b"CANARY_EXCERPT", value.encode("utf-8") if isinstance(value, str) else value, name)

        inspect(reader.trailer)

    def scan_tree(self, *private):
        excluded = {self.record.resolve(), *(path.resolve() for path in private)}
        for path in self.root.rglob("*"):
            if path.is_file() and path.resolve() not in excluded:
                self.scan(path.relative_to(self.root).as_posix(), path.read_bytes())

    def test_pandoc_writers_without_private_fields(self):
        # Some writers (e.g. chunkedhtml) were added after the oldest supported Pandoc.
        executable = shutil.which("pandoc")
        available = subprocess.run([executable, "--list-output-formats"], check=True, capture_output=True,
                                   encoding="utf-8").stdout.splitlines()
        from pdfmd_output import FORMAT_EXTENSION
        output_count = 0
        for writer, extension in FORMAT_EXTENSION.items():
            if writer not in available or writer == "pdf":
                continue
            with self.subTest(writer=writer):
                output = f"out-{writer}{extension if writer != 'chunkedhtml' else '.zip'}"
                result = self.run_build("draft.md", "--to", writer, "-o", output, "--no-cache")
                self.assertRegex(result.stdout + result.stderr, r"excerpts\.lua[^\n]*--citeproc")
                self.assertTrue((self.root / output).is_file())
                output_count += 1
        self.assertGreater(output_count, 10)
        self.scan_tree()

    def test_markdown_exports_prune_by_resolved_key_and_exclude_record_path_and_name(self):
        record = self.root / "private" / "notes.json"
        record.parent.mkdir()
        self.record.rename(record)
        self.record = record
        copy = self.write("also/notes.json", record.read_text(encoding="utf-8"))
        alias = self.root / "alias.json"
        try:
            alias.symlink_to(record)
        except (OSError, NotImplementedError):
            alias = record
        self.write("draft.md", """---
bibliography: refs.bib
pdfmd-options: {excerpts: private/notes.json}
---

[@x:1]. [Direct](private/notes.json). [Alias](alias.json).
""")
        self.run_build("draft.md", "--merge", "-o", "merged.md")
        self.run_build("draft.md", "--stop-at", "markdown", "-o", "assembled.md")
        self.run_build("draft.md", "--to", "gfm", "--keep-source", "readable", "--bundle", "all", "-o", "flat.md")
        for name in ("merged.md", "assembled.md", "flat.md"):
            self.assertIn("[@glass, p. 41]", (self.root / name).read_text(encoding="utf-8"), name)
        merged = (self.root / "merged.md").read_text(encoding="utf-8")
        self.assertIn("@book{glass", merged)
        self.assertNotIn("@book{unused", merged)
        self.assertNotIn("@book{clay", merged)
        self.run_build("--restore", "flat.md")
        self.scan_tree(copy, alias)

    def test_report_parallel_batch_and_parts(self):
        self.write("chapter.md", "Second chapter [@glass:2].\n")
        result = self.run_build("-r", "draft.md", "chapter.md", "--to", "html", "-o", "report.html")
        self.assertIn("excerpts.lua", result.stdout + result.stderr)
        for name in ("a", "b"):
            self.write(f"batch/{name}.md", f"The {name} claim [@x:1].\n")
        self.run_build("-b", "-j", "2", "batch/a.md", "batch/b.md", "--to", "html")
        self.write("parts/01.md", "\nPart [@x#1].\n")
        self.write("scaffold.md", "---\npdfmd-options: {parts: parts}\nbibliography: refs.bib\n---\n\nScaffold.\n")
        self.run_build("scaffold.md", "--to", "html", "-o", "parts.html")
        for name in ("report.html", "parts.html", "batch/a.html", "batch/b.html"):
            path = self.root / name
            self.assertIn('data-cites="glass"', path.read_text(encoding="utf-8"), name)
        self.scan_tree()

    def test_without_lua_package_warns_once_and_builds(self):
        self.write("sitecustomize.py", """import sys
from importlib.abc import MetaPathFinder
class OmitLua(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "pdfmd_lua" or fullname.startswith("pdfmd_lua."):
            raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0, OmitLua())
""")
        env = {**self.env, "PYTHONPATH": str(self.root)}
        result = self.build("draft.md", "--to", "html", "-o", "out.html", *self.flags, env=env)
        self.assertEqual((result.stdout + result.stderr).count("pdfmd_lua package is not installed"), 1)
        self.scan_tree()

    @unittest.skipUnless(shutil.which("pdflatex"), "needs pdfLaTeX")
    def test_private_attachment_round_trip_keeps_only_the_record_private(self):
        try:
            from pypdf import PdfReader
        except ImportError:
            self.skipTest("needs pypdf")
        record = self.record.read_bytes()
        self.record.unlink()
        marker_text = "Citation [@x#1]. Next [@glass:2, Table 4]."
        base = "---\nbibliography: refs.bib\npdfmd-options: {excerpts: records/reading.json"
        flags = ("-e", "pdflatex", "--engine-fallback", "off")
        note = "excerpt records (passages and notes) travel inside the PDF"
        for mode, args in (("command", ("--attach-source", "private")), ("bundle", ("--bundle",)),
                           ("all", ("--bundle", "all"))):
            with self.subTest(mode=mode):
                self.write(f"{mode}/records/reading.json", record.decode("utf-8"))
                self.write(f"{mode}/refs.bib", (self.root / "refs.bib").read_text(encoding="utf-8"))
                self.write(f"{mode}/draft.md", base + "}\n---\n\n" + marker_text + "\n")
                name = f"{mode}.pdf"
                result = self.run_build(f"{mode}/draft.md", *flags, *args, "-o", name)
                notices = [line for line in (result.stdout + result.stderr).splitlines() if note in line]
                self.assertEqual(len(notices), 1, notices)
                self.assertTrue(notices[0].startswith("NOTE "), notices)
                reader = PdfReader(self.root / name)
                text = "".join(page.extract_text() for page in reader.pages)
                self.assertIn("41", text)
                self.scan("PDF text", text.encode("utf-8"))
                self.scan("PDF metadata", str(reader.metadata).encode("utf-8"))
                self.assertEqual(list(reader.attachments["excerpts.json"]), [record])
                self.assertIn(marker_text.encode("utf-8"), reader.attachments[pdfmd.ATTACH_SOURCE][0])
                for key, values in reader.attachments.items():
                    if key != "excerpts.json":
                        for data in values:
                            self.scan(key, data)
                self.run_build(name, "-o", f"restored-{mode}")
                restored = self.root / f"restored-{mode}"
                self.assertEqual((restored / "excerpts.json").read_bytes(), record)
                self.assertIn(marker_text, (restored / "draft.md").read_text(encoding="utf-8"))
                self.run_build(f"restored-{mode}/draft.md", *flags, "--no-attach-source", "-o", f"rebuilt-{mode}.pdf")
                rebuilt = PdfReader(self.root / f"rebuilt-{mode}.pdf")
                self.assertEqual("".join(page.extract_text() for page in rebuilt.pages), text)
                self.assertFalse(rebuilt.attachments)

    def test_pdf_bundle_and_plain_attachment_comment_policies(self):
        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            self.skipTest("needs pypdf")
        record = self.record.read_bytes()
        comment = b"<!-- A draft comment. -->"
        marker = b"[@x:1]"
        self.write("draft.md", "---\nbibliography: refs.bib\n---\n\n"
                   "Citation [@x:1]. <!-- A draft comment. -->\n\n[Hidden]{.hide}\n")
        self.write("extra.md", "Extra [@x:1]. <!-- A draft comment. -->\n")
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.add_attachment("excerpts.json", record)
        writer.write(self.root / "earlier.pdf")
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.add_attachment("files/earlier.pdf", (self.root / "earlier.pdf").read_bytes())
        writer.write(self.root / "nested.pdf")
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.write(self.root / "ordinary.pdf")
        flags = ("-e", "inkmd", "--engine-fallback", "off")
        cases = (
            ("default", ("--attach-source",), False, False, False),
            ("bundle", ("--bundle", "all"), True, True, True),
            ("strip", ("--bundle", "all", "--strip-comments"), False, False, True),
            ("keep-kind", ("--attach-source", "--keep-comments-in", "Excerpts"), False, True, False),
            ("override", ("--attach-source", "private", "--strip-comments-in", "excerpts"), False, False, False),
        )
        for name, args, comments, excerpts, sweep in cases:
            with self.subTest(name=name):
                result = self.run_build("draft.md", *flags, *args, "-o", "out.pdf")
                pdf = self.root / "out.pdf"
                reader = PdfReader(pdf)
                attachments = {key: values[0] for key, values in reader.attachments.items()}
                source = attachments[pdfmd.ATTACH_SOURCE]
                self.assertEqual(comment in source, comments)
                self.assertEqual(marker in source, excerpts)
                self.assertIn(b"[Hidden]{.hide}", source)
                self.assertEqual(attachments.get("excerpts.json"), record if excerpts else None)
                self.assertEqual("files/earlier.pdf" in attachments, sweep and excerpts)
                self.assertEqual("files/nested.pdf" in attachments, sweep and excerpts)
                self.assertEqual("files/ordinary.pdf" in attachments, sweep)
                self.assertEqual("NOTE  " in result.stdout and "travel inside the PDF" in result.stdout, sweep or excerpts)
                if sweep:
                    self.run_build("--restore", "out.pdf", "-o", f"{name}.restored")
                    extra = (self.root / f"{name}.restored" / "extra.md").read_bytes()
                    self.assertEqual(comment in extra, comments)
                    self.assertEqual(marker in extra, excerpts)
                if not excerpts:
                    self.scan(name, pdf.read_bytes())

    def test_excerpt_comment_policy_uses_all_settings_layers(self):
        document = self.write("project/draft.md", "Text.\n")
        metadata = self.write("project/metadata.yaml", "{}\n")
        folder = self.write("project/.pdfmd/config.yaml", "{}\n")
        for layer in ("document", "metadata", "folder", "config"):
            for policy in ("false", "{Excerpts: false}", "true", "[Excerpts]", "{Excerpts: true}"):
                with self.subTest(layer=layer, policy=policy):
                    options = f"strip-comments: {policy}"
                    document.write_text(f"---\npdfmd-options: {{{options}}}\n---\n"
                                        if layer == "document" else "Text.\n", encoding="utf-8")
                    metadata.write_text(f"pdfmd-options: {{{options}}}\n" if layer == "metadata" else "{}\n",
                                        encoding="utf-8")
                    folder.write_text(f"options: {{{options}}}\n" if layer == "folder" else "{}\n", encoding="utf-8")
                    config = {"strip-comments": pdfmd.yaml.safe_load(policy)} if layer == "config" else {}
                    pdfmd.folder_walk.cache_clear()
                    with mock.patch.object(pdfmd, "config_options", return_value=config):
                        for shortcut in (frozenset(), frozenset({"excerpts"})):
                            strips = "excerpts" in pdfmd.resolve_strip_comments(document, [metadata], default=True,
                                                                               default_keep=shortcut)
                            self.assertEqual(strips, "false" not in policy)

    @unittest.skipUnless(shutil.which("pdflatex"), "needs pdfLaTeX")
    def test_latex_pdf_attachments_and_kept_intermediates(self):
        try:
            from pypdf import PdfReader
        except ImportError:
            self.skipTest("needs pypdf")
        self.run_build("draft.md", "-e", "pdflatex", "--engine-fallback", "off", "--attach-source",
                       "--cache", "--keep-aux", "-o", "latex.pdf")
        self.run_build("--restore", "latex.pdf")
        reader = PdfReader(self.root / "latex.pdf")
        self.assertIn("41", reader.pages[0].extract_text())
        self.assertTrue(reader.attachments)
        self.assertTrue(list(self.root.rglob("*.tex")), "no intermediate was kept")
        self.assertTrue(list(self.cache.rglob("*.log")) or list(self.cache.rglob("*.txt")), "no build record was found")
        self.scan_tree()

    @unittest.skipUnless(shutil.which("typst"), "needs Typst")
    def test_typst_pdf_and_writer(self):
        self.run_build("draft.md", "-e", "typst", "--engine-fallback", "off", "-o", "typst.pdf")
        self.run_build("draft.md", "--to", "typst", "-o", "out.typ")
        self.assertIn("41", (self.root / "out.typ").read_text(encoding="utf-8"))
        self.scan_tree()

    @unittest.skipUnless(pdfmd.resolve_soffice(), "needs LibreOffice")
    @unittest.skipIf(os.environ.get("CODEX_SANDBOX"), "LibreOffice cannot run in the sandbox")
    def test_bridge_and_hybrid(self):
        try:
            from pypdf import PdfReader
        except ImportError:
            self.skipTest("needs pypdf")
        self.run_build("draft.md", "-e", "soffice", "--engine-fallback", "off", "-o", "bridge.pdf")
        latex = shutil.which("pdflatex") or shutil.which("lualatex")
        if latex:
            self.run_build("draft.md", "--hybrid", "-e", Path(latex).stem, "-o", "hybrid.pdf")
            self.assertIn("Original.odt", PdfReader(self.root / "hybrid.pdf").attachments)
        self.scan_tree()


class NativeCanary(ResolverFixture, unittest.TestCase):
    def test_inkmd_uses_detached_citations(self):
        try:
            from pypdf import PdfReader
        except ImportError:
            self.skipTest("needs pypdf")
        self.write("draft.md", "A claim [@x:1].\n")
        self.build("draft.md", "-e", "inkmd", "-o", "native.pdf", "--no-backup", "--no-stamp", env={"PATH": ""})
        text = PdfReader(self.root / "native.pdf").pages[0].extract_text()
        self.assertIn("@glass, p. 41", text)
        self.assertNotIn("CANARY_EXCERPT", text)


if __name__ == "__main__":
    unittest.main()
