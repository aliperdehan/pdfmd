"""The filters pdfmd adds for one engine: pdfmd_lua/typst.lua (v3.27.11: links to anchors the document does not have,
pictures with an older Pandoc) and pdfmd_lua/weasyprint.lua (v3.27.12: math WeasyPrint cannot draw; v3.28.11: typeset
by KaTeX when `pdfmd --install math:katex` put it in place)."""

from __future__ import annotations

import io
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
TYPST = shutil.which("typst")
WEASYPRINT = shutil.which("weasyprint")
TYPST_LUA = ROOT / "lib" / "pdfmd_lua" / "typst.lua"
WEASYPRINT_LUA = ROOT / "lib" / "pdfmd_lua" / "weasyprint.lua"
NODE = shutil.which("node")
# the KaTeX this machine has (`pdfmd --install math:katex`), for the tests that typeset with it
KATEX = pdfmd.katex_runtime()

DOCUMENT = """\
# Head {#h}

Intro.

::: {#d}
A div.
:::

A [span]{#s} here.

``` {#c}
code
```

[to the head](#h) [to the div](#d) [to the span](#s) [to the code](#c) [gone](#nope) [again](#nope)
[web](https://example.org/)
"""


def tiny_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-typst-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def convert(self, writer: str) -> subprocess.CompletedProcess:
        source = self.directory / "doc.md"
        source.write_text(DOCUMENT, encoding="utf-8")
        return subprocess.run([PANDOC, str(source), "-t", writer, "--lua-filter", str(TYPST_LUA)], capture_output=True,
                              text=True, encoding="utf-8")

    def test_links_to_labels_stay_and_the_others_become_text(self):
        done = self.convert("typst")
        self.assertEqual(done.returncode, 0, done.stderr)
        for kept in ("#link(<h>)", "#link(<d>)", "#link(<s>)", '#link("https://example.org/")'):
            self.assertIn(kept, done.stdout)
        self.assertNotIn("<c>)", done.stdout)                      # a code block's id is no Typst label
        self.assertNotIn("<nope>", done.stdout)
        self.assertIn("to the code", done.stdout)
        self.assertIn("gone", done.stdout)
        self.assertEqual(done.stderr.count("WARN"), 1)
        self.assertIn("3 links to anchors that are not in the document (#c, #nope)", done.stderr)

    def standalone_typst(self, front: str, *extra: str) -> str:
        source = self.directory / "indent.md"
        source.write_text(f"---\ntitle: T\n{front}---\n\n# H\n\nOne.\n\nTwo.\n", encoding="utf-8")
        done = subprocess.run([PANDOC, str(source), "-s", "-t", "typst", *extra, "--lua-filter", str(TYPST_LUA)],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_the_documents_indent_reaches_typst(self):
        """v3.33.42: `indent: true` indents in LaTeX; Pandoc's Typst template has no such variable, so typst.lua sets it."""
        rule = "#set par(first-line-indent: 1.5em)"
        self.assertIn(rule, self.standalone_typst("indent: true\n"))
        self.assertIn(rule, self.standalone_typst("indent: \"yes\"\n"))
        self.assertNotIn(rule, self.standalone_typst("indent: false\n"))
        self.assertNotIn(rule, self.standalone_typst(""))

    def test_the_space_between_paragraphs(self):
        """v3.33.58: `indent: true` gives Typst LaTeX's spacing (one line: the leading), and paragraph-spacing
        (`pdfmd-paragraph-spacing`) is added to it; v3.33.73: the leading is LaTeX's line pitch less the line box, and
        without either Typst's own room (1.2em - 0.65em) is added to it."""
        def rules(front: str, *extra: str) -> list[str]:
            return [line for line in self.standalone_typst(front, *extra).splitlines() if "spacing" in line and "#" in line]

        self.assertEqual(rules(""), ["#set par(leading: 0.5317em, spacing: 0.5317em + 0.55em)"])
        self.assertEqual(rules("indent: false\n"), ["#set par(leading: 0.5317em, spacing: 0.5317em + 0.55em)"])
        self.assertEqual(rules("indent: true\n"), ["#set par(leading: 0.5317em, spacing: 0.5317em)"])
        self.assertEqual(rules("indent: true\nlinestretch: 1.5\n"), ["#set par(leading: 1.1476em, spacing: 1.1476em)"])
        self.assertEqual(rules("indent: true\n", "-V", "linestretch=2"), ["#set par(leading: 1.7635em, spacing: 1.7635em)"])
        self.assertEqual(rules("", "-M", "pdfmd-paragraph-spacing=6pt"),
                         ["#set par(leading: 0.5317em, spacing: 0.5317em + 6pt)"])
        self.assertEqual(rules("indent: true\n", "-M", "pdfmd-paragraph-spacing=1em"),
                         ["#set par(leading: 0.5317em, spacing: 0.5317em + 1em)"])
        self.assertEqual(rules("", "-M", "pdfmd-paragraph-spacing=0pt"), ["#set par(leading: 0.5317em, spacing: 0.5317em)"])

    def test_the_line_spacing_is_latexs(self):
        """v3.33.73: lines linestretch x the class's \\baselineskip apart (10, 11, 12 pt: 12, 13.6, 14.5 TeX points; 1.2 x
        another size), less the line box of 0.7em, in Typst's points; a -V variable over the metadata; at the top of
        the body, after the template's own leading; none in a fragment."""
        def leading(front: str, *extra: str) -> str:
            text = self.standalone_typst(front, *extra)
            found = re.findall(r"#set par\(leading: ([0-9.]+em),", text)
            self.assertEqual(len(found), 1, text)
            self.assertIn('#set text(top-edge: 0.7em, bottom-edge: "baseline")', text)
            self.assertLess(text.index("#show: doc => conf("), text.index("#set par(leading:"))
            self.assertLess(text.index("#set par(leading:"), text.index("One."))
            return found[0]

        self.assertEqual(leading(""), "0.5317em")                         # the template's 11pt
        self.assertEqual(leading("fontsize: 10pt\n"), "0.4955em")
        self.assertEqual(leading("fontsize: 12pt\n"), "0.5038em")
        self.assertEqual(leading("fontsize: 12pt\nlinestretch: 2\n"), "1.7076em")
        self.assertEqual(leading("fontsize: 10pt\nlinestretch: 1.5\n"), "1.0933em")
        self.assertEqual(leading("fontsize: 14pt\n"), "0.4955em")       # no class size: 1.2 x the size
        self.assertEqual(leading("fontsize: 12pt\n", "-V", "fontsize=10pt"), "0.4955em")
        source = self.directory / "fragment.md"
        source.write_text("One.\n", encoding="utf-8")
        done = subprocess.run([PANDOC, str(source), "-t", "typst", "--lua-filter", str(TYPST_LUA)],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("leading", done.stdout)

    def test_reference_entries_are_spaced_in_lines(self):
        """v3.33.59: the `refs` div's CSL entry-spacing N becomes the leading plus N lines; Pandoc's template wrote
        `spacing: Nem`, edge to edge, so 0 printed one entry's first line on the previous one's last."""
        def rules(attributes: str, identifier: str = "refs") -> list[str]:
            source = self.directory / "refs.md"
            source.write_text(f"::: {{#{identifier} .references .csl-bib-body {attributes}}}\nAn entry.\n:::\n",
                              encoding="utf-8")
            done = subprocess.run([PANDOC, str(source), "-t", "typst", "--lua-filter", str(TYPST_LUA)],
                                  capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(done.returncode, 0, done.stderr)
            return [line for line in done.stdout.splitlines() if "spacing" in line]

        self.assertEqual(rules('entry-spacing="0"'), ["#show: body => context { set par(spacing: par.leading); body }"])
        self.assertEqual(rules('entry-spacing="2"'), ["#show: body => context { set par(spacing: par.leading + 2 * "
                                                      "(par.leading + measure[X].height)); body }"])
        self.assertEqual(rules('entry-spacing="2.5"'), [])               # Pandoc's template writes no spacing for it
        self.assertEqual(rules(""), [])
        self.assertEqual(rules('entry-spacing="0"', "other"), [])

    @unittest.skipUnless(TYPST, "needs Typst")
    def test_the_spacing_rule_compiles(self):
        source = self.directory / "spaced.md"
        source.write_text("---\nindent: true\n---\n\nOne.\n\nTwo.\n", encoding="utf-8")
        done = subprocess.run([PANDOC, str(source), "-o", str(self.directory / "spaced.pdf"), "--pdf-engine=typst",
                               "-M", "pdfmd-paragraph-spacing=6pt", "--lua-filter", str(TYPST_LUA)],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_other_writers_are_untouched(self):
        done = self.convert("html")
        self.assertIn('href="#nope"', done.stdout)
        self.assertNotIn("WARN", done.stderr)

    def test_weasyprint_gets_a_table_style_while_pandocs_own_is_in(self):
        # v3.28.3: Pandoc's screen style set a narrow table's caption a syllable a line in WeasyPrint
        source = self.directory / "styled.md"
        source.write_text("---\nheader-includes: |\n  ```{=html}\n  <meta name=\"own\" content=\"kept\">\n  ```\n---\n\n"
                          "| a |\n|---|\n| 1 |\n\n: Caption\n", encoding="utf-8")
        (self.directory / "own.css").write_text("", encoding="utf-8")

        def page(*extra: str) -> str:
            done = subprocess.run([PANDOC, str(source), "-s", "-t", "html5", "--lua-filter", str(WEASYPRINT_LUA), *extra],
                                  capture_output=True, text=True, encoding="utf-8", cwd=self.directory)
            self.assertEqual(done.returncode, 0, done.stderr)
            return done.stdout

        plain = page()
        self.assertIn("min-width: 4in", plain)
        self.assertIn('name="own"', plain)                           # the document's own header-includes stay
        self.assertNotIn("min-width: 4in", page("--css", "own.css"))  # a stylesheet of one's own replaces Pandoc's
        self.assertNotIn("min-width: 4in", page("-t", "typst"))

    def test_a_label_used_twice_is_kept_by_the_first_element(self):
        # v3.28.2: "label <fig:tlc> occurs multiple times" stopped a lab report through the LaTeX filter
        source = self.directory / "twice.md"
        source.write_text("::: {#x}\nFirst.\n:::\n\n# Second {#x}\n\n[link](#x)\n", encoding="utf-8")
        done = subprocess.run([PANDOC, str(source), "-t", "typst", "--lua-filter", str(TYPST_LUA)], capture_output=True,
                              text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.count("<x>"), 2)                 # the div's label and the link to it
        self.assertIn("1 label on more than one element (x)", done.stderr)


@unittest.skipUnless(PANDOC and TYPST, "needs Pandoc and Typst")
class CommandLine(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-typst-cli-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def run_pdfmd(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.directory,
                              env={**os.environ, "PDFMD_NO_PROMPT": "1"})

    def test_a_link_to_a_missing_anchor_does_not_stop_the_pdf(self):
        (self.directory / "doc.md").write_text(DOCUMENT, encoding="utf-8")
        done = self.run_pdfmd("doc.md", "-e", "typst")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.directory / "doc.pdf").is_file())
        self.assertIn("links to anchors that are not in the document", done.stdout + done.stderr)

    def test_a_picture_is_found_when_pandoc_runs_in_the_metadata_files_folder(self):
        # pdfmd runs Pandoc in the first metadata file's folder; a Pandoc before 3.2 did not find the picture there
        (self.directory / "pictures").mkdir()
        (self.directory / "pictures" / "dot.png").write_bytes(tiny_png())
        (self.directory / "shared").mkdir()
        (self.directory / "shared" / "meta.yaml").write_text("lang: en\n", encoding="utf-8")
        (self.directory / "doc.md").write_text("# A\n\n![A dot](pictures/dot.png)\n", encoding="utf-8")
        done = self.run_pdfmd("doc.md", "-y", "shared/meta.yaml", "-e", "typst")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.directory / "doc.pdf").is_file())
        typ = self.run_pdfmd("doc.md", "-y", "shared/meta.yaml", "-t", "typst", "-o", "doc.typ")
        self.assertEqual(typ.returncode, 0, typ.stdout + typ.stderr)
        self.assertIn('image("pictures/dot.png"', (self.directory / "doc.typ").read_text(encoding="utf-8"))

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_reference_entries_do_not_overlap(self):
        """v3.33.59: with a CSL's entry-spacing 0 the entries' lines are the document's line spacing apart (each entry's
        first line was printed on the previous entry's last); with 1 one line more, as LaTeX's \\itemsep does."""
        words = " ".join(["word"] * 40)
        (self.directory / "refs.bib").write_text("".join(f"@book{{k{n}, title={{Entry {n} {words}}}, year={{2000}}}}\n"
                                                         for n in range(3)), encoding="utf-8")
        for spacing, apart in (("0", 1), ("1", 2)):
            with self.subTest(entry_spacing=spacing):
                (self.directory / "style.csl").write_text(
                    '<?xml version="1.0" encoding="utf-8"?>\n<style xmlns="http://purl.org/net/xbiblio/csl" '
                    'class="in-text" version="1.0"><info><title>T</title><id>t</id><updated>2026-01-01T00:00:00+00:00'
                    '</updated></info><citation><layout><text variable="title"/></layout></citation>'
                    f'<bibliography entry-spacing="{spacing}"><sort><key variable="title"/></sort><layout>'
                    '<text variable="title"/></layout></bibliography></style>\n', encoding="utf-8")
                (self.directory / "doc.md").write_text("---\nbibliography: refs.bib\ncsl: style.csl\nlinestretch: 2\n"
                                                       "nocite: '@*'\n---\n", encoding="utf-8")
                done = self.run_pdfmd("doc.md", "-e", "typst")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                layout = subprocess.run(["pdftotext", "-bbox-layout", str(self.directory / "doc.pdf"), "-"],
                                        capture_output=True, text=True, encoding="utf-8").stdout
                lines = [(float(top), first) for top, first in re.findall(
                    r'<line xMin="[^"]+" yMin="([^"]+)".*?<word[^>]*>([^<]*)', layout, re.S) if first != "1"]  # no page number
                tops = [top for top, _ in lines]
                firsts = [index for index, (_, first) in enumerate(lines) if first == "Entry"]
                pitches = [round(after - before, 1) for before, after in zip(tops, tops[1:])]
                self.assertEqual(len(firsts), 3)
                self.assertGreater(len(tops), 6)                                # the entries wrap
                line = min(pitches)
                for index, pitch in enumerate(pitches, 1):
                    self.assertAlmostEqual(pitch, line * (apart if index in firsts else 1), delta=0.2, msg=pitches)

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_lines_are_latexs_line_pitch_apart(self):
        """v3.33.73: a Typst PDF's lines are LaTeX's linestretch x \\baselineskip apart (a TeX point is 72/72.27 of
        Typst's), in two fonts; a paragraph break adds paragraph-spacing to it; a raw rule later in the text still wins."""
        words = " ".join(["word"] * 120)
        cases = (("fontsize: 12pt\nlinestretch: 2\n", 2 * 14.5), ("fontsize: 10pt\n", 12.0),
                 ("fontsize: 11pt\nlinestretch: 1.5\nmainfont: Times New Roman\n", 1.5 * 13.6))
        for front, pitch in cases:
            with self.subTest(front=front):
                (self.directory / "doc.md").write_text(f"---\n{front}---\n\nFirst {words}\n\nSecond {words}\n",
                                                       encoding="utf-8")
                done = self.run_pdfmd("doc.md", "-e", "typst", "--paragraph-spacing", "6pt")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                tops = self.line_tops()
                second = [first for _, first in tops].index("Second")
                pitches = [round(after - before, 2) for (before, _), (after, _) in zip(tops, tops[1:])]
                for index, apart in enumerate(pitches[:4] + pitches[second:second + 3]):
                    self.assertAlmostEqual(apart, pitch * 72 / 72.27, delta=0.05, msg=pitches)
                self.assertAlmostEqual(pitches[second - 1], pitch * 72 / 72.27 + 6, delta=0.05, msg=pitches)
        (self.directory / "doc.md").write_text(f"---\nfontsize: 12pt\n---\n\nFirst {words}\n\n```{{=typst}}\n"
                                               f"#set par(leading: 2em)\n```\n\nSecond {words}\n", encoding="utf-8")
        done = self.run_pdfmd("doc.md", "-e", "typst")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        tops = self.line_tops()
        second = [first for _, first in tops].index("Second")
        self.assertAlmostEqual(tops[second + 1][0] - tops[second][0], 12 * 2.7, delta=0.05)    # 2em + the 0.7em box

    @unittest.skipUnless(shutil.which("pdftotext") and shutil.which("lualatex"), "needs pdftotext and LuaLaTeX")
    def test_title_abstract_and_toc_use_the_body_pitch(self):
        source = self.directory / "doc.md"
        source.write_text("---\ntitle: Titlefirst " + "title " * 12 +
                          "\nfontsize: 12pt\nlinestretch: 2\nmainfont: STIX Two Text\nabstract: Abstractfirst " +
                          "abstractword " * 20 + "\n---\n\n# Headingfirst " + "heading " * 10 +
                          "\n\nBodyfirst " + "bodyword " * 80 + "\n\n# Headingsecond\n\nLast.\n", encoding="utf-8")
        environment = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                       "XDG_CONFIG_HOME": str(self.directory / "config"),
                       "XDG_CACHE_HOME": str(self.directory / "cache"), "XDG_DATA_HOME": str(self.directory / "data")}
        lines = {}
        for engine in ("lualatex", "typst"):
            output = self.directory / (engine + ".pdf")
            done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), str(source), "-e", engine,
                                   "--toc", "--no-stamp", "--no-backup", "-o", str(output)],
                                  env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            layout = subprocess.check_output(["pdftotext", "-bbox-layout", str(output), "-"], text=True)
            lines[engine] = [(float(top), first) for top, first in re.findall(
                r'<line xMin="[^"]+" yMin="([^"]+)".*?<word[^>]*>([^<]*)', layout, re.S)]

        def pitch(engine, word):
            found = lines[engine]
            index = next(i for i, (_, first) in enumerate(found) if first == word)
            return found[index + 1][0] - found[index][0]

        body = pitch("lualatex", "Bodyfirst")
        self.assertAlmostEqual(pitch("typst", "Bodyfirst"), body, delta=0.05)
        for word, size_ratio in (("Titlefirst", 1.5), ("Abstractfirst", 1), ("Headingfirst", 1)):
            with self.subTest(region=word):
                self.assertAlmostEqual(pitch("typst", word) / size_ratio, body, delta=0.05)

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_custom_template_spacing_wins_property_by_property(self):
        (self.directory / "doc.md").write_text(
            "---\nfontsize: 12pt\nlinestretch: 2\n---\n\nFirst  \nline\n\nSecond  \nline\n", encoding="utf-8")
        folder = self.directory / "custom templates"
        folder.mkdir()
        template = folder / "own.typ"
        environment = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                       "XDG_CONFIG_HOME": str(self.directory / "config"),
                       "XDG_CACHE_HOME": str(self.directory / "cache"), "XDG_DATA_HOME": str(self.directory / "data")}
        default_leading = (2 * 14.5 * 72 / 72.27) - 0.7 * 12
        cases = (("", default_leading + 8.4, default_leading + 15),
                 ("#set par(leading: 2em)", 32.4, default_leading + 15),
                 ("#set par(leading: 1.3em)", 24, default_leading + 15),
                 ("#set par(spacing: 30pt)", default_leading + 8.4, 38.4),
                 ("#set text(top-edge: 1em)", default_leading + 12, default_leading + 18.6),
                 ("#set text(bottom-edge: -0.2em)", default_leading + 10.8, default_leading + 17.4),
                 ("#show: body => { set par(leading: 2em, spacing: 30pt); body }", 32.4, 38.4))
        for rules, pitch, gap in cases:
            with self.subTest(rules=rules):
                template.write_text('#set text(size: 12pt)\n' + rules + '\n$body$\n', encoding="utf-8")
                self.check_template_pitch(environment, ["--template", str(template)], pitch, gap)
        (folder / "nested").mkdir()
        (folder / "nested" / "piece.typ").write_text('#set par(spacing: 30pt)\n\n', encoding="utf-8")
        template.write_text('#set text(size: 12pt)\n#set par(leading: 2em)\n$nested/piece.typ()$\n$body$\n', encoding="utf-8")
        defaults = folder / "defaults.yaml"
        defaults.write_text('template: "${.}/own.typ"\n', encoding="utf-8")
        for options in (["--template=" + str(template)], ["--defaults", str(defaults)]):
            with self.subTest(options=options):
                self.check_template_pitch(environment, options, 32.4, 38.4)
        defaults_folder = Path(environment["XDG_DATA_HOME"]) / "pandoc" / "defaults"
        defaults_folder.mkdir(parents=True)
        (defaults_folder / "base.yaml").write_text("template: " + str(template) + "\n", encoding="utf-8")
        (defaults_folder / "house.yaml").write_text('defaults: ["${.}/base.yaml"]\n', encoding="utf-8")
        self.check_template_pitch(environment, ["--defaults", "house"], 32.4, 38.4)

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_default_template_body_still_resets_header_edges(self):
        (self.directory / "doc.md").write_text(
            '---\nfontsize: 12pt\nlinestretch: 2\nheader-includes: |\n'
            '  ```{=typst}\n  #set text(top-edge: 1em)\n  ```\n---\n\nFirst  \nline\n\nSecond  \nline\n', encoding="utf-8")
        environment = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                       "XDG_CONFIG_HOME": str(self.directory / "config"),
                       "XDG_CACHE_HOME": str(self.directory / "cache"), "XDG_DATA_HOME": str(self.directory / "data")}
        pitch = 2 * 14.5 * 72 / 72.27
        self.check_template_pitch(environment, [], pitch, pitch + 0.55 * 12)

    def check_template_pitch(self, environment, options, pitch, gap):
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "doc.md", "-e", "typst",
                               "--no-stamp", "--no-backup", *options], cwd=self.directory, env=environment,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        tops = self.line_tops()
        self.assertAlmostEqual(tops[1][0] - tops[0][0], pitch, delta=0.05, msg=tops)
        self.assertAlmostEqual(tops[2][0] - tops[1][0], gap, delta=0.05, msg=tops)

    def line_tops(self) -> list[tuple[float, str]]:
        layout = subprocess.run(["pdftotext", "-bbox-layout", str(self.directory / "doc.pdf"), "-"],
                                capture_output=True, text=True, encoding="utf-8").stdout
        page = layout.split("</page>")[0]
        return [(float(top), first) for top, first in re.findall(
            r'<line xMin="[^"]+" yMin="([^"]+)".*?<word[^>]*>([^<]*)', page, re.S)]

    def test_the_filter_is_given_only_to_typst(self):
        self.assertEqual(pdfmd.typst_filter_args("latex"), [])
        self.assertEqual(pdfmd.typst_filter_args("typst")[-1], str(TYPST_LUA))


class WeasyPrintArguments(unittest.TestCase):
    def test_plain_math_and_the_filter_only_for_weasyprint(self):
        self.assertEqual(pdfmd.weasyprint_math_args("typst", []), [])
        arguments = pdfmd.weasyprint_math_args("weasyprint", [])
        self.assertEqual(arguments[-1], str(ROOT / "lib" / "pdfmd_lua" / "weasyprint.lua"))
        if pdfmd.pandoc_has_option("--math-method"):
            self.assertIn("--math-method=plain", arguments)

    def test_the_command_lines_math_wins(self):
        arguments = pdfmd.weasyprint_math_args("weasyprint", ["--mathml"])
        self.assertFalse([item for item in arguments if item.startswith("--math")])
        self.assertIn("--lua-filter", arguments)
        self.assertFalse([item for item in arguments if item.startswith("pdfmd-katex")])

    def test_katex_and_node_are_named_to_the_filter(self):
        folder = Path(tempfile.mkdtemp(prefix="pdfmd-katex-"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        with mock.patch.object(pdfmd, "katex_runtime", return_value=("/opt/node/bin/node", folder)):
            arguments = pdfmd.weasyprint_math_args("weasyprint", [])
            chosen = pdfmd.weasyprint_math_args("weasyprint", ["--math-method=mathml"])
        self.assertIn(f"pdfmd-katex={folder}", arguments)
        self.assertIn(f"pdfmd-katex-url={folder.as_uri()}", arguments)
        self.assertIn("pdfmd-katex-node=/opt/node/bin/node", arguments)
        self.assertEqual(arguments[-2:], ["--lua-filter", str(WEASYPRINT_LUA)])
        if pdfmd.pandoc_has_option("--math-method"):
            self.assertIn("--math-method=plain", arguments)         # what KaTeX does not reach stays text
        self.assertFalse([item for item in chosen if item.startswith("pdfmd-katex")])


class KatexInstall(unittest.TestCase):
    """The pieces of `pdfmd --install math:katex` that need no network."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-katex-install-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def package(self, names: list[str]) -> Path:
        archive = self.directory / "katex.tgz"
        with tarfile.open(archive, "w:gz") as bundle:
            for name in names:
                data = name.encode()
                member = tarfile.TarInfo(name)
                member.size = len(data)
                bundle.addfile(member, io.BytesIO(data))
        return archive

    def test_only_the_script_stylesheet_fonts_mhchem_and_licence_are_kept(self):
        archive = self.package(["package/LICENSE", "package/README.md", "package/package.json",
                                "package/dist/katex.min.js", "package/dist/katex.js", "package/dist/katex.min.css",
                                "package/dist/katex.mjs", "package/dist/fonts/KaTeX_Main-Regular.woff2",
                                "package/dist/fonts/KaTeX_Main-Regular.ttf", "package/dist/contrib/mhchem.min.js",
                                "package/dist/contrib/copy-tex.min.js", "package/src/katex.ts", "../escape.js"])
        target = self.directory / "data" / "katex" / "0.18.9"
        target.mkdir(parents=True)
        (target / "old.js").write_text("left from before", encoding="utf-8")
        pdfmd.unpack_katex(archive, target)
        kept = sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file())
        self.assertEqual(kept, ["LICENSE", "contrib/mhchem.min.js", "fonts/KaTeX_Main-Regular.ttf",
                                "fonts/KaTeX_Main-Regular.woff2", "katex.min.css", "katex.min.js"])
        self.assertFalse((self.directory / "escape.js").exists())
        self.assertFalse(target.with_name("0.18.9.part").exists())

    def test_a_package_without_fonts_is_refused(self):
        archive = self.package(["package/dist/katex.min.js", "package/dist/katex.min.css"])
        target = self.directory / "katex" / "0.18.9"
        with self.assertRaises(OSError):
            pdfmd.unpack_katex(archive, target)
        self.assertFalse(target.exists())
        self.assertFalse(target.with_name("0.18.9.part").exists())

    def test_the_pinned_release_else_the_newest_installed(self):
        root = self.directory / "pdfmd" / "katex"
        for version in ("0.9.0", "0.16.11", "0.10.2"):
            (root / version).mkdir(parents=True)
            for name in ("katex.min.js", "katex.min.css"):
                (root / version / name).write_text("", encoding="utf-8")
        (root / "1.0.0").mkdir()                                    # incomplete: not a candidate
        with mock.patch.object(pdfmd, "data_root", return_value=self.directory / "pdfmd"):
            self.assertEqual(pdfmd.katex_folder(), root / "0.16.11")
            (root / pdfmd.KATEX_VERSION).mkdir()
            for name in ("katex.min.js", "katex.min.css"):
                (root / pdfmd.KATEX_VERSION / name).write_text("", encoding="utf-8")
            self.assertEqual(pdfmd.katex_folder(), root / pdfmd.KATEX_VERSION)
            with mock.patch.object(pdfmd, "which", return_value=None):
                self.assertIsNone(pdfmd.katex_runtime())             # KaTeX without node: no typesetting
        with mock.patch.object(pdfmd, "data_root", return_value=self.directory / "nothing"):
            self.assertIsNone(pdfmd.katex_folder())

    def test_nodes_release_names(self):
        self.assertEqual(pdfmd.node_asset_name("v24.21.0", "Darwin", "arm64"), "node-v24.21.0-darwin-arm64.tar.xz")
        self.assertEqual(pdfmd.node_asset_name("v24.21.0", "Linux", "x86_64"), "node-v24.21.0-linux-x64.tar.xz")
        self.assertEqual(pdfmd.node_asset_name("v24.21.0", "Windows", "AMD64"), "node-v24.21.0-win-x64.zip")
        self.assertIsNone(pdfmd.node_asset_name("v24.21.0", "FreeBSD", "x86_64"))

    def test_node_is_taken_from_its_bin_folder(self):
        archive = self.directory / "node.tar.xz"
        with tarfile.open(archive, "w:xz") as bundle:
            for name, data in (("node-v1/lib/node_modules/x/node", b"not this"), ("node-v1/bin/node", b"this")):
                member = tarfile.TarInfo(name)
                member.size = len(data)
                bundle.addfile(member, io.BytesIO(data))
        target = pdfmd.extract_executable(archive, "node", self.directory / "bin", inside="bin")
        self.assertEqual(target.read_bytes(), b"this")

    def test_the_kind_is_math_katex(self):
        self.assertEqual(pdfmd.install_kind("math:katex"), "math:katex")
        self.assertEqual(pdfmd.install_kind("math"), "math")
        with self.assertRaises(Exception):
            pdfmd.install_kind("math:mathjaxx")                         # math:mathjax is MathJax (tests/test_mathjax.py)

    def test_weasyprints_css_complaints_are_dropped(self):
        said = ("WARNING: Ignored `text-rendering: optimizeLegibility` at 22:7, unknown property.\n"
                "WARNING: Expected a media type, got '(max-width: 600px)'\n"
                "WARNING: Invalid media type ' (max-width: 600px) ' the whole @media rule was ignored at 25:5.\n"
                "WARNING: Ignored `width:min-content` at 1:5629, invalid value.\n"
                "WARNING: Failed to load image at 'file:///x.png': No such file\n"
                "WARN  weasyprint: KaTeX could not typeset 1 of 2 formulas\n")
        self.assertEqual(pdfmd.WEASYPRINT_CSS_NOISE.sub("", said),
                         "WARNING: Failed to load image at 'file:///x.png': No such file\n"
                         "WARN  weasyprint: KaTeX could not typeset 1 of 2 formulas\n")


@unittest.skipUnless(PANDOC and WEASYPRINT, "needs Pandoc and WeasyPrint")
class WeasyPrintMath(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-weasy-math-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def build(self, text: str) -> subprocess.CompletedProcess:
        (self.directory / "doc.md").write_text(text, encoding="utf-8")
        nothing = str(self.directory / "no-data")                   # no KaTeX installed: math as text
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-e", "weasyprint"], capture_output=True,
                              text=True, encoding="utf-8", cwd=self.directory,
                              env={**os.environ, "PDFMD_NO_PROMPT": "1", "XDG_DATA_HOME": nothing, "LOCALAPPDATA": nothing})

    def test_math_is_text_once_and_said_once(self):
        done = self.build("---\ntitle: M\n---\n\nSee $\\alpha_i \\le \\beta$ and $x^2 + \\frac{a}{b}$.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        said = done.stdout + done.stderr
        self.assertEqual(said.count("WeasyPrint does not typeset math"), 1)
        self.assertIn("2 formulas are printed as text", said)
        self.assertIn("pdfmd --install math:katex", said)
        self.assertNotIn("WARNING: Ignored", said)                  # WeasyPrint's CSS complaints (v3.28.11)
        if shutil.which("pdftotext"):
            text = subprocess.run(["pdftotext", str(self.directory / "doc.pdf"), "-"], capture_output=True,
                                  text=True, encoding="utf-8", errors="replace").stdout
            self.assertIn("α", text)
            self.assertNotIn("x2+ab", text)                    # MathML's flat text, before the TeX, is gone

    def test_no_math_no_warning(self):
        done = self.build("---\ntitle: M\n---\n\nJust words.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("typeset math", done.stdout + done.stderr)

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_a_narrow_tables_caption_breaks_between_words(self):
        # v3.28.3: "Ta / ble / 1: / A / rat / her" at the width of a one-column table
        done = self.build("---\ntitle: M\n---\n\n| a |\n|---|\n| 1 |\n\n: A rather long caption for a narrow table\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        text = subprocess.run(["pdftotext", str(self.directory / "doc.pdf"), "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        self.assertIn("A rather long caption for a narrow table", " ".join(text.split()))



@unittest.skipUnless(PANDOC and WEASYPRINT and KATEX, "needs Pandoc, WeasyPrint, node and `pdfmd --install math:katex`")
class WeasyPrintKatex(unittest.TestCase):
    """v3.28.11: with KaTeX installed, a WeasyPrint PDF's math is typeset in KaTeX's fonts."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-weasy-katex-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def build(self, text: str, *extra: str) -> subprocess.CompletedProcess:
        (self.directory / "doc.md").write_text(text, encoding="utf-8")
        # --no-auto mathjax: with MathJax installed too it would typeset first (tests/test_mathjax.py); these are KaTeX's
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-e", "weasyprint", "--no-auto", "mathjax",
                               *extra], capture_output=True, text=True, encoding="utf-8", cwd=self.directory,
                              env={**os.environ, "PDFMD_NO_PROMPT": "1"})

    def fonts(self) -> str:
        return subprocess.run(["pdffonts", str(self.directory / "doc.pdf")], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout

    def text(self) -> str:
        return subprocess.run(["pdftotext", str(self.directory / "doc.pdf"), "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout

    @unittest.skipUnless(shutil.which("pdffonts") and shutil.which("pdftotext"), "needs Poppler")
    def test_math_is_typeset_without_a_word_said(self):
        done = self.build("---\ntitle: K\n---\n\nSee $\\frac{a}{b} \\neq \\vec{v}$ and\n\n"
                          "$$\\sum_{n=1}^{\\infty} \\frac{1}{n^2} = \\frac{\\pi^2}{6}$$\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        said = done.stdout + done.stderr
        self.assertNotIn("typeset math", said)
        self.assertNotIn("KaTeX could not", said)
        self.assertNotIn("WARNING: Ignored", said)
        self.assertIn("KaTeX_Main", self.fonts())
        self.assertIn("KaTeX_Size", self.fonts())                  # the big sum sign
        self.assertNotIn("\\frac", self.text())

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_a_formula_katex_cannot_read_is_text_and_said_once(self):
        done = self.build("---\ntitle: K\n---\n\nGood $x^2$, bad $\\nosuchmacro{y}$.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        said = done.stdout + done.stderr
        self.assertEqual(said.count("KaTeX could not typeset 1 of 2 formulas"), 1, said)
        self.assertIn("\\nosuchmacro", said)
        self.assertIn("\\nosuchmacro{y}", self.text())

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
    def test_chemistry_in_math_is_converted_first(self):
        done = self.build("---\ntitle: K\n---\n\nWater $\\ce{2H2 + O2 -> 2H2O}$.\n", "-v")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("\\ce", self.text())
        self.assertNotIn("KaTeX could not", done.stdout + done.stderr)
        # KaTeX's own mhchem would hide the order: the command line shows it, the LaTeX filter first
        command = next(line for line in (done.stdout + done.stderr).splitlines()
                       if line.startswith("CMD") and "weasyprint.lua" in line)
        self.assertLess(command.index("office.lua"), command.index("weasyprint.lua"))

    @unittest.skipUnless(shutil.which("pdfinfo") and shutil.which("pdffonts"), "needs Poppler")
    def test_a_formula_in_the_title_stays_in_the_pdfs_title(self):
        # typeset, it is raw HTML, which the page's <title> (the PDF's Title) leaves out: "Energy  here"
        done = self.build("---\ntitle: Energy $E = mc^2$ here\n---\n\nWords.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        info = subprocess.run(["pdfinfo", str(self.directory / "doc.pdf")], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        self.assertIn("Energy E = mc^2 here", info)
        self.assertIn("KaTeX_Main", self.fonts())                  # on the page, typeset


if __name__ == "__main__":
    unittest.main()
