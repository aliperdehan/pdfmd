"""v3.33.71: `engine-fallback` decides what a PDF engine's failure does (lib/pdfmd_chain). Before it, any failure tried the next
engine and the degraded file (a Typst PDF after a LaTeX error in the document) replaced the good PDF already there, exit 0.
The default, auto, stops a build whose PDF exists at an error in the document and keeps that PDF byte for byte; an engine
that cannot run here still falls through, with a NOTE. The builds go through pdfmd itself."""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

import pdfmd  # noqa: E402
import pdfmd_chain as chain  # noqa: E402

PANDOC = shutil.which("pandoc")
LUALATEX = shutil.which("lualatex")
TYPST = shutil.which("typst")
GOOD = "---\ntitle: E\n---\n\nGood text.\n"
BAD = "---\ntitle: E\n---\n\nBad \\undefinedcommandxyz text.\n"
FAKE_LUALATEX = """#!/bin/sh
case "$1" in --version|-v) echo "This is LuaHBTeX, Version 1.24.0 (fake)"; exit 0;; esac
echo "fake lualatex: cannot start" >&2
exit 1
"""


def failed(stderr: str, code: int = 43) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["pandoc"], code, "", stderr)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Kinds(unittest.TestCase):
    def test_an_error_in_the_document_is_the_documents(self):
        self.assertEqual(chain.failure_kind("lualatex", failed("Error producing PDF.\n! Undefined control sequence.\nl.5 \\x"))[0],
                         "document")
        self.assertEqual(chain.failure_kind("xelatex", failed("! LaTeX Error: File `nosuch.sty' not found.\n"))[0], "document")
        self.assertEqual(chain.failure_kind("pdflatex", failed("! LaTeX Error: File `nosuch.cls' not found.\n"))[0], "document")
        self.assertEqual(chain.failure_kind("lualatex", subprocess.CompletedProcess(       # the direct .tex route's log
            ["lualatex"], 1, "./t.tex:1: Undefined control sequence.\n", "Undefined control sequence."))[0], "document")
        typst = "error: unknown variable: nosuch\n    ┌─ toPdf.typ:153:1\n    │\n153 │ #nosuch()\n"
        self.assertEqual(chain.failure_kind("typst", failed(typst)), ("document", "error: unknown variable: nosuch"))

    def test_file_line_errors_with_spaces_and_quotes(self):
        for name in ("./my paper.tex", '"./my paper.tex"', "./my paper.t\nex"):
            result = subprocess.CompletedProcess(["lualatex"], 1, f"{name}:12: Undefined control sequence.\n", "")
            self.assertEqual(chain.failure_kind("lualatex", result)[0], "document")

    def test_an_engine_that_cannot_run_is_the_engines(self):
        for engine, text, code in (
                ("lualatex", "Error producing PDF.\n", 43),                                     # no LaTeX error at all
                ("lualatex", "module 'luaotfload-main' not found\n! Fatal error\n", 43),        # a TEX_CAUSES signature
                ("pdflatex", "! I can't find the format file `pdflatex.fmt'!\n", 43),
                ("xelatex", "! I can't write on file `x.log'.\n", 43),
                ("lualatex", "", chain.PANDOC_PROGRAM_NOT_FOUND),
                ("typst", "error: failed to load font\n", 43),                                  # no place in the source
                ("weasyprint", "Traceback (most recent call last):\n", 1)):
            self.assertEqual(chain.failure_kind(engine, failed(text, code))[0], "engine", (engine, text))


class Modes(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.doc = Path(self.folder.name) / "d.md"

    def mode(self, front: str, cli=None):
        self.doc.write_text(f"---\n{front}\n---\n\nText.\n", encoding="utf-8")
        with mock.patch.object(pdfmd, "ENGINE_FALLBACK_CLI", cli):
            return chain.resolve_mode(self.doc, [])

    def test_the_command_line_the_document_and_the_default(self):
        self.assertEqual(self.mode("title: T"), ("auto", "default"))
        self.assertEqual(self.mode("pdfmd-options: {engine-fallback: missing}"), ("missing", "pdfmd-options"))
        self.assertEqual(self.mode("pdfmd-options: {engine-fallback: off}"), ("off", "pdfmd-options"))     # YAML's False
        self.assertEqual(self.mode("pdfmd-options: {engine-fallback: on}"), ("on", "pdfmd-options"))       # YAML's True
        self.assertEqual(self.mode("pdfmd-options: {engine-fallback: off}", cli="on"), ("on", "--engine-fallback"))

    def test_a_word_that_is_no_mode_warns_and_is_auto(self):
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(self.mode("pdfmd-options: {engine-fallback: sometimes}"), ("auto", "default"))
        self.assertIn("is not one of auto, on, missing, off", err.getvalue())

    def test_pinned_follows_resolve_engines(self):
        self.doc.write_text("---\npdfmd-options: {pdf-engine: typst}\n---\nText.\n", encoding="utf-8")
        for cli, expected in ((None, True), ("", False), ("xelatex", True)):           # a bare -e pins nothing
            with mock.patch.object(pdfmd, "ENGINE_CLI", cli):
                self.assertEqual(chain.pinned(self.doc, []), expected, cli)
        self.doc.write_text("Text.\n", encoding="utf-8")
        with mock.patch.object(pdfmd, "ENGINE_CLI", None), mock.patch.object(pdfmd, "config_options", lambda *a: {}):
            self.assertFalse(chain.pinned(self.doc, []))


class Mirror(unittest.TestCase):
    def test_the_engine_or_the_first_of_its_family_goes_first(self):
        engines = ["lualatex", "xelatex", "pdflatex", "latexmk", "typst", "weasyprint", "edge"]
        self.assertEqual(chain.mirrored(engines, "typst"), ["typst", "lualatex", "xelatex", "pdflatex", "latexmk", "weasyprint", "edge"])
        self.assertEqual(chain.mirrored(engines, "tectonic")[0], "xelatex")              # XeTeX
        self.assertEqual(chain.mirrored(engines, "context")[0], "lualatex")              # LuaTeX
        self.assertEqual(chain.mirrored(engines, "chrome")[0], "edge")                   # the browsers
        self.assertIsNone(chain.mirrored(["lualatex"], "prince"))

    def test_the_pdfs_producer_names_the_engine(self):
        from pypdf import PdfWriter
        cases = {("Typst 0.15.1 via pdfmd-cli", None): "typst", ("LaTeX via pandoc via pdfmd-cli", "LuaTeX-1.24.0"): "lualatex",
                 ("LaTeX via pandoc", "xdvipdfmx (20260317)"): "xelatex", (None, "pdfTeX-1.40.29"): "pdflatex",
                 ("pandoc 3.13 via pdfmd-cli", "WeasyPrint 69.0"): "weasyprint", (None, "Prince 17 (www.princexml.com)"): "prince",
                 ("Mozilla/5.0 HeadlessChrome/157.0 Edg/157.0", "Skia/PDF m157"): "edge", (None, "Skia/PDF m157"): "chrome",
                 ("Writer", "LibreOffice 26.2"): "soffice", ("calibre 9.16.0", "calibre 9.16.0"): "calibre",
                 ("groff version 1.24.1", "gropdf version 1.24.1"): "groff", ("Word", "Microsoft Word"): None}
        with tempfile.TemporaryDirectory() as folder:
            for (creator, producer), engine in cases.items():
                writer = PdfWriter()
                writer.add_blank_page(100, 100)
                writer.add_metadata({key: value for key, value in (("/Creator", creator), ("/Producer", producer)) if value})
                path = Path(folder) / "m.pdf"
                with open(path, "wb") as handle:
                    writer.write(handle)
                self.assertEqual(chain.from_metadata(path), engine, (creator, producer))


class Records(unittest.TestCase):
    """The newest record of a build that wrote this output and did not fall back; `~` in a record is the home folder."""

    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.root = Path(self.home.name).resolve()
        self.doc = self.root / "docs" / "r.md"
        self.doc.parent.mkdir()
        self.doc.write_text("Text.\n", encoding="utf-8")
        self.output = self.doc.with_suffix(".pdf")
        self.folder = self.root / "records"
        self.folder.mkdir()
        patcher = mock.patch.object(Path, "home", classmethod(lambda cls: self.root))
        patcher.start()
        self.addCleanup(patcher.stop)

    def record(self, name: str, result: str, output: str | None = None) -> None:
        output = "~/docs/r.pdf" if output is None else output
        (self.folder / name).write_text(f"pdfmd build record\nwhen:      2026-11-10 09:03:00\nresult:    {result}\n"
                                        f"output:    {output}\n\nlines\n", encoding="utf-8")

    def look(self):
        build = pdfmd.load_package("pdfmd_buildinfo.build")
        with mock.patch.object(build, "build_record_folders", lambda *a, **k: [self.folder]):
            return chain.from_records(self.doc, self.output)

    def test_a_good_record_names_its_engine_and_when(self):
        self.record("20261110-090300-ok.log", "ok  in 3.1 s  (lualatex)")
        self.assertEqual(self.look(), ("lualatex", "build record 2026-11-10 09:03"))

    def test_a_record_of_another_output_or_a_failed_build_is_not_read(self):
        self.record("20261110-090300-ok.log", "ok  in 3.1 s  (lualatex)", output="~/docs/other.pdf")
        self.record("20261110-090400-failed.log", "FAILED  in 3.1 s  (xelatex failed; engine-fallback auto stopped the build)")
        self.assertEqual(self.look(), (None, ""))

    def test_a_fallen_back_build_is_not_mirrored(self):
        self.record("20261110-090500-ok.log", "ok  in 9 s  (typst; lualatex, xelatex failed)")
        engine, why = self.look()
        self.assertIsNone(engine)
        self.assertIn("fell back (typst after lualatex, xelatex failed)", why)
        self.record("20261110-090300-ok.log", "ok  in 3.1 s  (lualatex)")        # an older good build is
        self.assertEqual(self.look()[0], "lualatex")


@unittest.skipUnless(PANDOC and LUALATEX, "needs Pandoc and LuaLaTeX")
class Builds(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name).resolve()

    def pdfmd(self, *args, env: dict | None = None) -> tuple[int, str]:
        environment = {**os.environ, "PDFMD_NO_PROMPT": "1", **(env or {})}
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), *args, "--no-backup"], capture_output=True, text=True,
                              cwd=self.folder, env=environment, stdin=subprocess.DEVNULL)
        return done.returncode, done.stdout + done.stderr

    def write(self, name: str, text: str) -> Path:
        path = self.folder / name
        path.write_text(text, encoding="utf-8")
        return path

    def fake_path(self) -> str:
        bin_folder = self.folder / "bin"
        bin_folder.mkdir()
        fake = bin_folder / "lualatex"
        fake.write_text(FAKE_LUALATEX, encoding="utf-8")
        fake.chmod(0o755)
        return f"{bin_folder}{os.pathsep}{os.environ.get('PATH', '')}"

    @unittest.skipUnless(TYPST, "needs Typst")
    def test_an_error_in_the_document_keeps_the_pdf_there_and_on_replaces_it(self):
        self.write("d.md", BAD)
        code, said = self.pdfmd("d.md", "-e", "lualatex,typst")                      # nothing there yet: the whole chain
        self.assertEqual(code, 0, said)
        self.assertIn("(typst; lualatex failed)", said)
        self.write("d.md", GOOD)
        code, said = self.pdfmd("d.md", "-e", "lualatex,typst")
        self.assertIn("(lualatex)", said)
        before = sha(self.folder / "d.pdf")
        self.write("d.md", BAD)
        code, said = self.pdfmd("d.md", "-e", "lualatex,typst", "--verbose")
        self.assertEqual(code, 1, said)
        self.assertEqual(sha(self.folder / "d.pdf"), before)
        self.assertIn("engine-fallback auto: an error in the document, so the build stops here", said)
        self.assertIn("(lualatex failed; engine-fallback auto stopped the build, d.pdf kept; --engine-fallback on tries the next "
                      "engine)", said)
        self.assertIn("ENGINE  engine-fallback auto: d.pdf exists and the engine is pinned", said)
        self.assertNotIn("typst failed", said)
        code, said = self.pdfmd("d.md", "-e", "lualatex,typst", "--engine-fallback", "on")
        self.assertEqual(code, 0, said)
        self.assertNotEqual(sha(self.folder / "d.pdf"), before)

    @unittest.skipUnless(TYPST and os.name != "nt", "needs Typst and a shell script for the fake engine")
    def test_an_engine_that_cannot_run_falls_through_unless_off(self):
        self.write("d.md", GOOD)
        self.pdfmd("d.md", "-e", "lualatex")
        before = sha(self.folder / "d.pdf")
        path = {"PATH": self.fake_path()}
        code, said = self.pdfmd("d.md", "-e", "lualatex,typst", "--engine-fallback", "off", env=path)
        self.assertEqual(code, 1, said)
        self.assertEqual(sha(self.folder / "d.pdf"), before)
        self.assertIn("engine-fallback off: no other engine is tried", said)
        code, said = self.pdfmd("d.md", "-e", "lualatex,typst", "--engine-fallback", "missing", env=path)
        self.assertEqual(code, 0, said)
        self.assertIn("NOTE", said)
        self.assertIn("lualatex counts as unusable here", said)
        self.assertIn("(typst; lualatex failed)", said)

    @unittest.skipUnless(TYPST, "needs Typst")
    def test_auto_starts_with_the_engine_that_made_the_pdf(self):
        self.write("d.md", GOOD)
        record = {"PDFMD_BUILD_LOG": "on"}                                              # the tests run with records off
        code, said = self.pdfmd("d.md", "-e", "typst", env=record)
        self.assertEqual(code, 0, said)
        code, said = self.pdfmd("d.md", "--verbose", env=record)
        self.assertIn("ENGINE  engine-fallback auto: d.pdf was made by typst (build record ", said)
        self.assertRegex(said, r"OK .*\(typst\)")
        self.write("e.md", GOOD)                                                         # no record: the PDF's own metadata
        code, said = self.pdfmd("e.md", "-e", "typst", env={"PDFMD_BUILD_LOG": "off"})
        code, said = self.pdfmd("e.md", "--verbose")
        self.assertIn("e.pdf was made by typst (the PDF's Producer/Creator); starting with typst", said)
        self.assertRegex(said, r"OK .*\(typst\)")

    def test_a_tex_file_compiled_directly_keeps_its_pdf(self):
        tex = self.write("t.tex", "\\documentclass{article}\\begin{document}Good.\\end{document}\n")
        code, said = self.pdfmd("t.tex")
        self.assertEqual(code, 0, said)
        before = sha(self.folder / "t.pdf")
        tex.write_text("\\documentclass{article}\\begin{document}Bad \\undefinedcommandxyz.\\end{document}\n", encoding="utf-8")
        code, said = self.pdfmd("t.tex")
        self.assertEqual(code, 1, said)
        self.assertEqual(sha(self.folder / "t.pdf"), before)
        self.assertNotIn("trying it through Pandoc", said)              # the Pandoc route would drop the command and build
        self.assertIn("t.pdf kept", said)

    def test_spaced_tex_name_stops_fallback(self):
        self.write("my paper.tex", "\\documentclass{article}\\begin{document}Bad \\undefinedcommandxyz.\\end{document}\n")
        output = self.folder / "my paper.pdf"
        output.write_bytes(b"previous output")
        code, said = self.pdfmd("my paper.tex", "--engine-fallback", "missing")
        self.assertNotEqual(code, 0, said)
        self.assertEqual(output.read_bytes(), b"previous output")
        self.assertNotIn("trying it through Pandoc", said)

    def test_keep_aux_compiles_in_place_and_still_keeps_the_pdf(self):
        # TeX opens the PDF itself in place and removes it when it stops: the old one is put back
        tex = self.write("k.tex", "\\documentclass{article}\\begin{document}One.\\newpage Two.\\end{document}\n")
        code, said = self.pdfmd("k.tex", "--keep-aux")
        self.assertEqual(code, 0, said)
        before = sha(self.folder / "k.pdf")
        tex.write_text("\\documentclass{article}\\begin{document}One.\\newpage Two \\undefinedcommandxyz.\\end{document}\n",
                       encoding="utf-8")
        code, said = self.pdfmd("k.tex", "--keep-aux")
        self.assertEqual(code, 1, said)
        self.assertEqual(sha(self.folder / "k.pdf"), before)
        self.assertEqual(sorted(path.name for path in self.folder.glob("*kept*")), [])          # nothing left beside it

    def test_a_batch_decides_per_document(self):
        self.write("a.md", GOOD)
        self.write("b.md", GOOD)
        code, said = self.pdfmd("-b", ".", "-e", "lualatex")
        self.assertEqual(code, 0, said)
        a_before, b_before = sha(self.folder / "a.pdf"), sha(self.folder / "b.pdf")
        self.write("a.md", BAD)
        self.write("b.md", GOOD.replace("Good", "Changed"))
        code, said = self.pdfmd("-b", ".", "-e", "lualatex")
        self.assertEqual(code, 1, said)
        self.assertEqual(sha(self.folder / "a.pdf"), a_before)
        self.assertNotEqual(sha(self.folder / "b.pdf"), b_before)
        self.assertIn("a.pdf kept", said)
        self.assertNotIn("b.pdf kept", said)


if __name__ == "__main__":
    unittest.main()
