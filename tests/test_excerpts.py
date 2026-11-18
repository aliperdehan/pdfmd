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
        for args, code in ((("show", "99"), 1), (("list", "--problems"), 2), (("remove", "1", "--detach"), 2),
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
    def pdf(self, name, words="Invented glass study", count=2, label=None):
        """Small PDFs made in the test, with synthetic text and real/trivial labels."""
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
        writer = pdfmd.pypdf.PdfWriter()
        for number in range(count):
            page = writer.add_blank_page(width=200, height=200)
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 10 Tf 10 180 Td ({words}; printed {41 + number}) Tj ET".encode("ascii"))
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
            page[NameObject("/Contents")] = writer._add_object(stream)
        if label:
            writer.set_page_label(0, count - 1, style="/D", start=label)
        path = self.root / name
        with path.open("wb") as handle:
            writer.write(handle)
        return path

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


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class BuildIsolation(CommandFixture, unittest.TestCase):
    def test_record_presence_has_no_build_effect_or_passage_leak(self):
        self.write("draft.md", "---\ntitle: Synthetic trial\nidentifier: urn:uuid:00000000-0000-4000-8000-000000000001\n---\n\nAn invented claim [@x:1].\n")
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


if __name__ == "__main__":
    unittest.main()
