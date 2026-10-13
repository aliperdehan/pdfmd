"""A header file of pdfmd's own no longer drops `header-includes:` (v3.27.18). Pandoc lets --include-in-header win
over them, so the code-wrapping header of any document with code, graphicx for a raw \\includegraphics, the fonts
header, preamble.tex and the packages header each threw away the document's own or a metadata file's: the first command
from them stopped LaTeX. The builds load a package (lipsum), not a \\newcommand: Pandoc expands those itself."""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

LIPSUM = "\\usepackage{lipsum}"
BODY = "\\lipsum[1][1]\n"
CODE = "\n```python\nprint(1)\n```\n"


def has_latex_package(name: str) -> bool:
    if not (shutil.which("lualatex") and shutil.which("kpsewhich") and shutil.which("pdftotext")):
        return False
    found = subprocess.run(["kpsewhich", f"{name}.sty"], capture_output=True, text=True)
    return found.returncode == 0 and bool(found.stdout.strip())


def png(path: Path) -> None:
    """A 1x1 white PNG."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff")) + chunk(b"IEND", b""))


class Folder(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-header-includes-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def write(self, name: str, text: str) -> Path:
        path = self.directory / name
        path.write_text(text, encoding="utf-8")
        return path


class WhatPandocKeeps(Folder):
    def test_the_documents_own_beat_every_metadata_file(self):
        doc = self.write("a.md", f"---\nheader-includes:\n  - {LIPSUM}\n---\n\nText.\n")
        meta = self.write("metadata.yaml", "header-includes:\n  - \\usepackage{house}\n")
        self.assertEqual(pdfmd.pandoc_header_includes([doc], [meta]), (LIPSUM, "document"))

    def test_the_later_metadata_file_and_the_later_source_win(self):
        doc = self.write("a.md", "Text.\n")
        first = self.write("first.yaml", "header-includes:\n  - \\usepackage{first}\n")
        second = self.write("second.yaml", "header-includes: |\n  \\usepackage{second}\n  \\input{chemicals}\n")
        self.assertEqual(pdfmd.pandoc_header_includes([doc], [first, second]),
                         ("\\usepackage{second}\n\\input{chemicals}", "metadata"))
        one = self.write("one.md", "---\nheader-includes: \\usepackage{one}\n---\n\nA.\n")
        two = self.write("two.md", "---\nheader-includes: \\usepackage{two}\n---\n\nB.\n")
        self.assertEqual(pdfmd.pandoc_header_includes([one, two, doc], []), ("\\usepackage{two}", "document"))

    def test_a_fenced_metadata_file_and_a_raw_latex_fence(self):
        doc = self.write("a.md", "Text.\n")
        meta = self.write("meta.yaml", "---\nheader-includes:\n  - |\n    ```{=latex}\n    \\usepackage{x}\n    ```\n---\n")
        self.assertEqual(pdfmd.pandoc_header_includes([doc], [meta]), ("\\usepackage{x}", "metadata"))

    def test_nothing(self):
        self.assertIsNone(pdfmd.pandoc_header_includes([self.write("a.md", "Text.\n")], []))

    def test_raw_blocks_and_spans_as_the_latex_writer_takes_them(self):
        # v3.27.19: the manual's own way of writing a header-includes item put the backticks in the preamble
        self.assertEqual(pdfmd.raw_latex_only("```{=latex}\n\\usepackage{x}\n```"), "\\usepackage{x}")
        self.assertEqual(pdfmd.raw_latex_only("~~~~ {=tex}\n\\usepackage{x}\n~~~~"), "\\usepackage{x}")
        self.assertEqual(pdfmd.raw_latex_only("```{=html}\n<style>p {}</style>\n```").strip(), "")
        self.assertEqual(pdfmd.raw_latex_only("`\\usepackage{y}`{=latex}`<b>`{=html}"), "\\usepackage{y}")
        self.assertEqual(pdfmd.raw_latex_only("\\usepackage{z} % plain"), "\\usepackage{z} % plain")
        doc = self.write("a.md", "---\nheader-includes:\n  - |\n    ```{=latex}\n    \\usepackage{x}\n    ```\n"
                                 "  - |\n    ```{=html}\n    <style>p {}</style>\n    ```\n  - \\usepackage{y}\n---\n\nText.\n")
        self.assertEqual(pdfmd.document_header_includes(doc.read_text(encoding="utf-8")), "\\usepackage{x}\n\\usepackage{y}")


class Placement(Folder):
    def command(self, *headers: str) -> list[str]:
        cmd = ["pandoc", "doc.md"]
        for header in headers:
            cmd += ["--include-in-header", header]
        return cmd + ["--lua-filter", "x.lua"]

    def headers(self, cmd: list[str]) -> list[str]:
        return [Path(cmd[index + 1]).name for index, item in enumerate(cmd[:-1]) if item == "--include-in-header"]

    def test_a_metadata_files_go_after_the_code_header_and_before_the_rest(self):
        doc = self.write("a.md", "Text.\n")
        meta = self.write("metadata.yaml", f"header-includes:\n  - {LIPSUM}\n")
        cmd = self.command("/x/code_wrap.tex", "/x/preamble.tex", "/x/fonts.tex")
        pdfmd.keep_header_includes(cmd, [doc], [meta], [])
        names = self.headers(cmd)
        self.assertEqual(names[0], "code_wrap.tex")
        self.assertTrue(names[1].startswith("header-includes-"), names)
        self.assertEqual(names[2:], ["preamble.tex", "fonts.tex"])
        self.assertIn(LIPSUM, Path(cmd[cmd.index("--include-in-header", 3) + 1]).read_text(encoding="utf-8"))

    def test_the_documents_own_go_last_but_before_the_packages_header(self):
        doc = self.write("a.md", f"---\nheader-includes:\n  - {LIPSUM}\n---\n\nText.\n")
        packages = str(pdfmd.cache_root() / "tex" / "packages-0123456789abcdef.tex")
        cmd = self.command("/x/code_wrap.tex", "/x/graphicx.tex", packages)
        pdfmd.keep_header_includes(cmd, [doc], [], [])
        names = self.headers(cmd)
        self.assertEqual(names[:2], ["code_wrap.tex", "graphicx.tex"])
        self.assertTrue(names[2].startswith("header-includes-"), names)
        self.assertEqual(names[3], Path(packages).name)
        cmd = self.command("/x/graphicx.tex")
        pdfmd.keep_header_includes(cmd, [doc], [], [])
        self.assertTrue(self.headers(cmd)[-1].startswith("header-includes-"))

    def test_left_alone(self):
        doc = self.write("a.md", f"---\nheader-includes:\n  - {LIPSUM}\n---\n\nText.\n")
        untouched = self.command()                                           # no header file: Pandoc keeps them
        pdfmd.keep_header_includes(untouched, [doc], [], [])
        self.assertEqual(untouched, self.command())
        for options in (["-H", "mine.tex"], ["-Hmine.tex"], ["--include-in-header=mine.tex"], ["-M", "header-includes=x"]):
            cmd = self.command("/x/code_wrap.tex")                           # the caller's own replaces them
            pdfmd.keep_header_includes(cmd, [doc], [], options)
            self.assertEqual(cmd, self.command("/x/code_wrap.tex"), options)
        cmd = self.command("/x/preamble.tex", "/x/doc-header.tex")           # document_header_file has them already
        pdfmd.keep_header_includes(cmd, [doc], [], [], Path("/x/doc-header.tex"))
        self.assertEqual(cmd, self.command("/x/preamble.tex", "/x/doc-header.tex"))


@unittest.skipUnless(shutil.which("pandoc") and has_latex_package("lipsum"), "needs Pandoc, lualatex with lipsum and pdftotext")
class Building(Folder):
    def build(self, name: str, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), name, "-e", "lualatex", *arguments],
                              capture_output=True, text=True, encoding="utf-8", cwd=self.directory,
                              env={**os.environ, "PDFMD_NO_PROMPT": "1"})

    def assert_built(self, name: str, *arguments: str) -> None:
        done = self.build(name, *arguments)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = subprocess.run(["pdftotext", str(self.directory / Path(name).with_suffix(".pdf")), "-"],
                              capture_output=True, text=True).stdout
        self.assertIn("Lorem ipsum", text)

    def test_the_documents_own_with_code(self):
        self.write("a.md", f"---\ntitle: A\nheader-includes:\n  - {LIPSUM}\n---\n\n{BODY}{CODE}")
        self.assert_built("a.md")

    def test_fenced_items_with_code(self):
        # a ```{=latex} item and an ```{=html} one: LaTeX gets the first without its fence and not the second
        self.write("a.md", "---\ntitle: A\nheader-includes:\n  - |\n    ```{=latex}\n    " + LIPSUM + "\n    ```\n"
                           "  - |\n    ```{=html}\n    <style>p {}</style>\n    ```\n---\n\n" + BODY + CODE)
        self.assert_built("a.md")

    def test_the_documents_own_with_a_raw_includegraphics(self):
        png(self.directory / "dot.png")
        self.write("a.md", f"---\ntitle: A\nheader-includes:\n  - {LIPSUM}\n---\n\n{BODY}\n\\includegraphics{{dot.png}}\n")
        self.assert_built("a.md")

    def test_a_metadata_files_with_code(self):
        self.write("metadata.yaml", f"header-includes: |\n  {LIPSUM}\n")
        self.write("a.md", f"---\ntitle: A\n---\n\n{BODY}{CODE}")
        self.assert_built("a.md")

    def test_a_metadata_files_beside_a_preamble(self):
        self.write("metadata.yaml", f"header-includes:\n  - {LIPSUM}\n")
        self.write("preamble.tex", "\\usepackage{xcolor}\n")
        self.write("a.md", f"---\ntitle: A\n---\n\n{BODY}")
        self.assert_built("a.md")

    def test_a_report_whose_first_chapter_has_its_own_and_code(self):
        self.write("one.md", f"---\ntitle: R\nheader-includes:\n  - {LIPSUM}\n---\n\n# One\n\n{BODY}{CODE}")
        self.write("two.md", "# Two\n\nMore.\n")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "-r", "one.md", "two.md", "-o", "r.pdf",
                               "-e", "lualatex"], capture_output=True, text=True, encoding="utf-8", cwd=self.directory,
                              env={**os.environ, "PDFMD_NO_PROMPT": "1"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_a_report_takes_the_first_chapters_macro_values(self):
        # v3.27.26: experiment: in the front matter sets \LabExperiment (document_latex_definitions) in a -r PDF too
        # v3.28.37: the key is the package's own (its pdfmd helper), found by reading the preamble's \usepackage
        package = self.directory / "tex" / "keypkg"
        package.mkdir(parents=True)
        (package / "keypkg.sty").write_text("\\ProvidesPackage{keypkg}\n\\newcommand{\\LabExperiment}{N/A}\n", encoding="utf-8")
        (package / "keypkg-pdfmd.yaml").write_text("latex-keys:\n  experiment: LabExperiment\n", encoding="utf-8")
        self.write("preamble.tex", "\\usepackage{keypkg}\n")
        self.write("one.md", "---\ntitle: R\nexperiment: 7\n---\n\n# One\n\nExperiment \\LabExperiment{} done.\n")
        self.write("two.md", "# Two\n\nMore.\n")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "-r", "one.md", "two.md", "-o", "r.pdf",
                               "-e", "lualatex"], capture_output=True, text=True, encoding="utf-8", cwd=self.directory,
                              env={**os.environ, "PDFMD_NO_PROMPT": "1", "TEXINPUTS": f"{self.directory / 'tex'}//:"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = subprocess.run(["pdftotext", str(self.directory / "r.pdf"), "-"], capture_output=True, text=True).stdout
        self.assertIn("Experiment 7 done", " ".join(text.split()))

    def test_a_header_file_of_the_callers_own_replaces_them_as_in_pandoc(self):
        self.write("mine.tex", "\\usepackage{xcolor}\n")
        self.write("a.md", f"---\ntitle: A\nheader-includes:\n  - {LIPSUM}\n---\n\n{BODY}")
        self.assertNotEqual(self.build("a.md", "-H", "mine.tex").returncode, 0)


class PreambleWithAPicture(Folder):
    """v3.27.25: a preamble that defines an environment around a tikzpicture was taken for a TikZ picture file and
    left out, and the build stopped at the environment's first use."""

    def test_a_definition_is_a_preamble_and_a_picture_is_not(self):
        cases = {
            "\\newenvironment{plot}{\\begin{tikzpicture}}{\\end{tikzpicture}}\n": True,
            "\\newcommand{\\dot}{\\begin{tikzpicture}\\fill (0,0) circle (1pt);\\end{tikzpicture}}\n": True,
            "% \\begin{tikzpicture} in a comment\n\\usepackage{tikz}\n": True,
            "\\begin{tikzpicture}\n\\draw (0,0) -- (1,1);\n\\end{tikzpicture}\n": False,      # a picture file
            "\\documentclass{article}\n": False,
        }
        for text, expected in cases.items():
            self.assertEqual(pdfmd.is_latex_preamble(self.write("preamble.tex", text)), expected, text)

    @unittest.skipUnless(shutil.which("pandoc") and has_latex_package("tikz"), "needs Pandoc, lualatex with TikZ")
    def test_it_builds(self):
        self.write("preamble.tex", "\\usepackage{tikz}\n\\newenvironment{plot}{\\begin{tikzpicture}}{\\end{tikzpicture}}\n")
        self.write("a.md", "---\ntitle: A\n---\n\nText.\n\n```{=latex}\n\\begin{plot}\\draw (0,0) -- (1,1);\\end{plot}\n```\n")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "a.md", "-e", "lualatex"], capture_output=True,
                              text=True, encoding="utf-8", cwd=self.directory, env={**os.environ, "PDFMD_NO_PROMPT": "1"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"FOUND .*preamble\.tex")


if __name__ == "__main__":
    unittest.main()
