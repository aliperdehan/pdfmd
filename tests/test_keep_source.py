"""`--keep-source` and `--restore FILE.md` (v3.26.4): the trailer's encodings (pure Python, no Pandoc) and the command line."""

from __future__ import annotations

import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

from pdfmd_flat import keep  # noqa: E402
from pandoc_support import needs_pandoc  # noqa: E402

NASTY = ("---\ntitle: T\n---\n\n<!-- a <!-- b --> c -->\r\n\n```\n--> and --!> and <!-- and \\> and \\\\\n```\n"
         "<!-- pdfmd-source 1\n== files/x.csv\n=equals first\n<lt first\n")


class Trailer(unittest.TestCase):
    def roundtrip(self, entries: dict[str, bytes], body: str = "Body.\n", mode: str = "packed"):
        trailer = keep.pack(entries, body, mode, "doc.md", "3.26.4")
        self.assertEqual(trailer.count("-->"), 1, "only the closing -->")
        self.assertNotIn("--!>", trailer)
        self.assertTrue(trailer.endswith("\n-->\n"))
        text = keep.append(body, trailer)
        found_body, found = keep.split(text)
        self.assertIsNotNone(found)
        self.assertEqual(found.mode, mode)
        self.assertEqual(keep.unpack(found), entries)
        self.assertEqual(keep.digest(found_body), found.body_hash)
        return text

    def test_both_encodings_survive_comments_closers_and_the_marker(self):
        entries = {"pdfmd-source.md": NASTY.encode(), "pdfmd-manifest.json": b"{}\n", "files/d.csv": b"a,b\r\n1,2\r\n"}
        for mode in keep.MODES:
            with self.subTest(mode=mode):
                self.roundtrip(entries, mode=mode)

    def test_crlf_and_binary_entries_come_back_byte_for_byte(self):
        entries = {"s.md": b"line one\r\nline two\r\n\r\n", "bin": bytes(range(256)), "empty": b"", "nl": b"\n\n"}
        for mode in keep.MODES:
            with self.subTest(mode=mode):
                self.roundtrip(entries, mode=mode)

    def test_a_huge_source(self):
        random.seed(7)
        words = ["alpha", "-->", "<!--", "--!>", "\\", ">", "\r\n", "\n=", "\n<", "x"]
        huge = "".join(random.choice(words) + " " for _ in range(400_000)).encode()
        self.assertGreater(len(huge), 1_000_000)
        for mode in keep.MODES:
            with self.subTest(mode=mode):
                self.roundtrip({"s.md": huge}, mode=mode)

    def test_random_text_roundtrips_in_readable_mode(self):
        random.seed(11)
        alphabet = ["\\", ">", "<", "=", "-", "\r", "\n", "a", " ", "!", "r", "é"]
        for _ in range(500):
            text = "".join(random.choice(alphabet) for _ in range(random.randint(0, 60)))
            self.assertEqual(keep.unescape(keep.escape(text)), text)
            escaped = keep.escape(text)
            self.assertNotRegex(escaped, r"(?<!\\)>")        # every > carries its backslash: no --> or --!> is left
            self.assertNotIn("-->", escaped)
            self.assertNotIn("\r", escaped)
            self.assertFalse(any(line.startswith(("<", "=")) for line in escaped.split("\n")))

    def test_the_last_marker_wins_over_one_in_the_body(self):
        body = "Docs.\n\n```\n<!-- pdfmd-source 1\nencoding: packed\n\nAAAA\n-->\n```\n"
        text = self.roundtrip({"s.md": b"real"}, body=body)
        found_body, found = keep.split(text)
        self.assertIn("```\n<!-- pdfmd-source 1", found_body)
        self.assertEqual(keep.unpack(found), {"s.md": b"real"})

    def test_a_file_with_no_trailer(self):
        self.assertIsNone(keep.find("Just text.\n"))
        self.assertIsNone(keep.find("Text.\n\n<!-- a comment -->\n"))
        self.assertEqual(keep.split("Just text.\n"), ("Just text.\n", None))

    def test_a_flat_file_that_already_has_a_trailer_is_kept_whole_inside_the_next(self):
        first = self.roundtrip({"s.md": b"inner"})
        for mode in keep.MODES:
            with self.subTest(mode=mode):
                outer = self.roundtrip({"pdfmd-source.md": first.encode()}, body="Outer.\n", mode=mode)
                _, trailer = keep.split(outer)
                self.assertEqual(keep.unpack(trailer)["pdfmd-source.md"].decode(), first)

    def test_edited_body_changes_the_hash(self):
        text = self.roundtrip({"s.md": b"x"}, body="Body.\n")
        body, trailer = keep.split(text.replace("Body.", "Body, edited."))
        self.assertNotEqual(keep.digest(body), trailer.body_hash)

    def test_damaged_and_newer_trailers_say_so(self):
        text = keep.append("B.\n", keep.pack({"s.md": b"x"}, "B.\n"))
        lines = text.split("\n")
        damaged = "\n".join(lines[:-3] + ["AAAA", "-->", ""])
        _, trailer = keep.split(damaged)
        with self.assertRaises(keep.KeepError):
            keep.unpack(trailer)
        with self.assertRaisesRegex(keep.KeepError, "newer pdfmd"):
            keep.find(text.replace("pdfmd-source 1", "pdfmd-source 99"))


@needs_pandoc(3, 1, 3)
class CommandLine(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-keep-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.env = {**os.environ, "PDFMD_CONFIG": "", "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"]}

    def run_pdfmd(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory, env=self.env)

    def write(self, name: str, text: str) -> Path:
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def document(self, extra: str = "") -> Path:
        self.write("data.csv", "Name,Mass\nWater,18.02\n")
        return self.write("doc.md", f'''---
title: T
{extra}---

Water is H~2~O.

<!-- a <!-- b --> c -->

::: {{.csv file="data.csv"}}
:::

```
--> and --!>
```
''')

    def test_keep_source_then_restore(self):
        self.document("pdfmd-options:\n  strip-comments: false\n")
        for mode in keep.MODES:
            with self.subTest(mode=mode):
                result = self.run_pdfmd("doc.md", "--to", "gfm", "--keep-source", mode, "-o", f"{mode}.md")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("KEPT", result.stdout)
                text = (self.directory / f"{mode}.md").read_text(encoding="utf-8")
                body, trailer = keep.split(text)
                self.assertEqual(trailer.mode, mode)
                self.assertIn("H₂O", body)
                self.assertNotIn("--!>", text.split(keep.MARKER)[-1])
                restored = self.run_pdfmd("--restore", f"{mode}.md")
                self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
                source = (self.directory / f"{mode}.restored" / "doc.md").read_text(encoding="utf-8")
                self.assertIn("<!-- a <!-- b --> c -->", source)
                self.assertIn("--> and --!>", source)
                self.assertEqual((self.directory / f"{mode}.restored" / "data.csv").read_text(), "Name,Mass\nWater,18.02\n")

    def test_restore_never_overwrites_and_can_list(self):
        self.document()
        self.assertEqual(self.run_pdfmd("doc.md", "--to", "gfm", "--keep-source", "-o", "k.md").returncode, 0)
        listing = self.run_pdfmd("--restore", "k.md", "--list")
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertIn("SOURCE    doc.md", listing.stdout)
        self.assertFalse((self.directory / "k.restored").exists())
        self.assertEqual(self.run_pdfmd("--restore", "k.md").returncode, 0)
        again = self.run_pdfmd("--restore", "k.md")
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("nothing was written", again.stdout + again.stderr)

    def test_an_edited_body_is_noted_and_the_source_still_comes_back(self):
        self.document()
        self.run_pdfmd("doc.md", "--to", "gfm", "--keep-source", "-o", "k.md")
        path = self.directory / "k.md"
        path.write_text(path.read_text(encoding="utf-8").replace("# T", "# Edited title", 1), encoding="utf-8")
        result = self.run_pdfmd("--restore", "k.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("edited since pdfmd wrote it", result.stderr)
        self.assertIn("title: T", (self.directory / "k.restored" / "doc.md").read_text(encoding="utf-8"))

    def test_the_document_option_and_no_keep_source(self):
        self.document("pdfmd-options:\n  keep-source: readable\n")
        self.run_pdfmd("doc.md", "--to", "gfm", "-o", "a.md")
        self.assertEqual(keep.split((self.directory / "a.md").read_text(encoding="utf-8"))[1].mode, "readable")
        self.run_pdfmd("doc.md", "--to", "gfm", "--no-keep-source", "-o", "b.md")
        self.assertIsNone(keep.split((self.directory / "b.md").read_text(encoding="utf-8"))[1])

    def test_no_source_in_a_plain_file(self):
        self.write("plain.md", "Just text.\n")
        result = self.run_pdfmd("--restore", "plain.md")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("keeps no pdfmd source", result.stdout + result.stderr)

    def test_a_part_alone_keeps_nothing(self):
        self.write("report.md", "---\ntitle: P\npdfmd-options:\n  parts: auto\n  keep-source: true\n---\n")
        self.write("parts/10-one.md", "# One\n\nText.\n")
        self.write("parts/20-two.md", "# Two\n\nText.\n")
        self.assertEqual(self.run_pdfmd("report#two", "--to", "gfm", "-o", "two.md").returncode, 0)
        self.assertIsNone(keep.split((self.directory / "two.md").read_text(encoding="utf-8"))[1])
        self.assertEqual(self.run_pdfmd("report", "--to", "gfm", "-o", "all.md").returncode, 0)
        self.assertIsNotNone(keep.split((self.directory / "all.md").read_text(encoding="utf-8"))[1])


if __name__ == "__main__":
    unittest.main()
