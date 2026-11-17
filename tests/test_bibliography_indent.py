"""`bibliography-indent`: one hanging indent for the reference list and for the entries `fullcite` places, in every writer
(pdfmd_bibliography, pdfmd_lua/bibliography_indent.lua; pdfmd_office writes the Word and OpenDocument styles)."""

from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

LUA = ROOT / "lib" / "pdfmd_lua"
PANDOC = shutil.which("pandoc")
BIB = ("@book{a, author={Alpha, Ann}, title={First Book With A Title Long Enough To Wrap Over More Than One Line}, year={1984}, "
       "publisher={Press}}\n@book{b, author={Beta, Bob}, title={Second Book}, year={1990}, publisher={Press}}\n")
BODY = "See [@a; @b].\n\n# References\n\n::: {#refs}\n:::\n"


class Values(unittest.TestCase):
    def setUp(self):
        self.package = pdfmd.load_package("pdfmd_bibliography")

    def test_what_is_taken(self):
        normalise = self.package.normalise
        for value, expected in (("0.5in", "0.5in"), ("1.5em", "1.5em"), (" 2 CM ", "2cm"), (".5in", ".5in"), (0, "0pt"), ("0", "0pt"),
                                ("0em", "0pt"), ("auto", None), ("", None), (None, None)):
            self.assertEqual(normalise(value), expected, value)
        for value in ("1", 1, "-1em", "3px", True, False, "wide"):
            with self.assertRaises(ValueError, msg=value):
                normalise(value)

    def test_the_layers(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            document = root / "d.md"
            document.write_text("---\ntitle: T\n---\n\nx\n", encoding="utf-8")
            metadata = root / "meta.yaml"
            metadata.write_text("pdfmd-options:\n  bibliography-indent: 0.5in\n", encoding="utf-8")
            self.assertIsNone(self.package.setting(document, []))
            self.assertEqual(self.package.setting(document, [metadata]), "0.5in")
            document.write_text("---\npdfmd-options:\n  bibliography-indent: 0\n---\n\nx\n", encoding="utf-8")
            self.assertEqual(self.package.setting(document, [metadata]), "0pt")
            document.write_text("---\npdfmd-options:\n  bibliography-indent: auto\n---\n\nx\n", encoding="utf-8")
            self.assertIsNone(self.package.setting(document, []))
            document.write_text("---\npdfmd-options:\n  bibliography-indent: wide\n---\n\nx\n", encoding="utf-8")
            with self.assertRaises(SystemExit) as caught:
                self.package.setting(document, [])
            self.assertIn("pdfmd-options.bibliography-indent must be a length", str(caught.exception))

    def test_the_command_line_wins(self):
        with tempfile.TemporaryDirectory() as folder:
            document = Path(folder) / "d.md"
            document.write_text("---\npdfmd-options:\n  bibliography-indent: 0.5in\n---\n\nx\n", encoding="utf-8")
            old = os.environ.pop(self.package.ENV, None)
            try:
                os.environ[self.package.ENV] = "2cm"
                self.assertEqual(self.package.setting(document, []), "2cm")
                os.environ[self.package.ENV] = "auto"
                self.assertIsNone(self.package.setting(document, []))                 # auto on the command line beats the file
                with self.assertRaises(SystemExit) as caught:
                    self.package.command_line_value("wide")
                self.assertIn("--bibliography-indent must be a length", str(caught.exception))
            finally:
                os.environ.pop(self.package.ENV, None)
                if old is not None:
                    os.environ[self.package.ENV] = old

    def test_the_filter_goes_in_when_set_and_for_typst(self):
        with tempfile.TemporaryDirectory() as folder:
            document = Path(folder) / "d.md"
            document.write_text("---\ntitle: T\n---\n\nx\n", encoding="utf-8")
            args = pdfmd.bibliography_indent_args
            self.assertEqual(args(document, [], [], [], "typst"), [])                     # no citeproc, nothing to change
            spacing = ["--lua-filter", str(LUA / "bibliography_spacing.lua")]
            self.assertEqual(args(document, [], ["--citeproc"], [], "latex"), spacing)    # no indent override
            self.assertEqual(args(document, [], ["--citeproc"], [], "docx"), spacing)
            typst = args(document, [], ["--citeproc"], [], "typst")
            self.assertEqual(typst, ["-M", "pdfmd-bibliography-indent-default=1.5em", "--lua-filter", str(LUA / "bibliography_indent.lua"), *spacing])
            document.write_text("---\npdfmd-options:\n  bibliography-indent: 0.5in\n---\n\nx\n", encoding="utf-8")
            self.assertEqual(args(document, [], ["--citeproc"], [], "docx")[:2], ["-M", "pdfmd-bibliography-indent=0.5in"])
            self.assertEqual(args(document, [], [], ["--citeproc"], "html")[:2], ["-M", "pdfmd-bibliography-indent=0.5in"])


class OfficeStyles(unittest.TestCase):
    """What pdfmd_office writes into the `pdfmd-hang-<length>` styles, on small synthetic files (Pandoc's own odt route)."""

    def test_word_hangs_the_whole_indent(self):
        from pdfmd_office import docx_post
        styles = ('<w:styles><w:style w:type="paragraph" w:customStyle="1" w:styleId="pdfmd-hang-1p5em"><w:name w:val="pdfmd-hang-1p5em"/>'
                  '<w:basedOn w:val="BodyText"/></w:style></w:styles>')
        done, count = docx_post.style_hangs(styles)
        self.assertEqual(count, 1)
        self.assertIn('<w:ind w:left="360" w:hanging="360"/>', done)

    def test_an_odt_gets_a_margin_and_a_negative_text_indent(self):
        import pdfmd_office
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.odt"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("content.xml", '<office:text><text:p text:style-name="pdfmd-hang-0p5in">x</text:p></office:text>')
                archive.writestr("styles.xml", "<office:styles></office:styles>")
            self.assertEqual(pdfmd_office.finish_odt(path), 1)
            styles = zipfile.ZipFile(path).read("styles.xml").decode()
            self.assertIn('style:name="pdfmd-hang-0p5in"', styles)
            self.assertIn('fo:margin-left="0.5000in" fo:text-indent="-0.5000in"', styles)


@unittest.skipUnless(PANDOC, "needs Pandoc")
class NoAbbreviation(unittest.TestCase):
    def test_a_pandoc_option_that_starts_a_pdfmd_one_is_a_pass_through(self):
        """argparse would read `--bibliography` as an abbreviation of a longer pdfmd option (`--bibliography-indent`) and the build
        would stop, where the option is Pandoc's. Every Pandoc long option that is a unique start of a pdfmd one is registered as a
        pass-through (an exact option beats an abbreviation; DECISION 82)."""
        from pdfmd_args import PASS_THROUGH, PassThrough
        help_text = subprocess.run([PANDOC, "--help"], capture_output=True, text=True, encoding="utf-8").stdout
        pandoc_options = set(re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]*)", help_text))
        self.assertGreater(len(pandoc_options), 50)
        actions = pdfmd.build_parser()._option_string_actions
        ours = {option for option, action in actions.items() if option.startswith("--") and not isinstance(action, PassThrough)}
        # exactly one longer option: argparse takes it (two or more it calls ambiguous, which pdfmd already meets for
        # `--ascii` and `--metadata`, and has handled since before this check)
        swallowed = {option for option in pandoc_options - ours
                     if len([name for name in ours if name.startswith(option)]) == 1}
        self.assertEqual(swallowed, set(PASS_THROUGH))
        for option in PASS_THROUGH:
            self.assertIsInstance(actions[option], PassThrough)

    def test_the_tokens_reach_pandoc_where_they_stood(self):
        arguments = ["d.md", "--bibliography", "a.bib", "--bibliography-indent", "2cm", "-M", "bibliography=c.bib",
                     "--bibliography=b.bib", "--wrap=none", "--", "--bibliography"]
        named, pandoc = pdfmd.build_parser().parse_known_args(arguments)
        self.assertEqual(named.bibliography_indent, "2cm")
        self.assertFalse(hasattr(named, "pandoc_bibliography"))
        self.assertEqual(pandoc, ["--bibliography", "a.bib", "-M", "bibliography=c.bib", "--bibliography=b.bib", "--wrap=none",
                                  "--", "--bibliography"])
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            pdfmd.build_parser().parse_known_args(["--bib", "a.bib"])           # two options start so: ambiguous


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "refs.bib").write_text(BIB, encoding="utf-8")
        (self.root / "t.md").write_text("---\nbibliography: refs.bib\n---\n\n" + BODY, encoding="utf-8")

    def run_pandoc(self, to: str, *meta: str, output: str | None = None) -> subprocess.CompletedProcess:
        command = [PANDOC, "t.md", "-f", "markdown", "-t", to, "--citeproc", "--lua-filter", str(LUA / "bibliography_indent.lua")]
        for item in meta:
            command += ["-M", item]
        if output:
            command += ["-o", output]
        return subprocess.run(command, cwd=self.root, capture_output=True, text=True, encoding="utf-8")

    def out(self, to: str, *meta: str) -> str:
        done = self.run_pandoc(to, *meta)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_latex_sets_the_length_the_template_reads(self):
        self.assertIn("\\setlength{\\cslhangindent}{0.5in}", self.out("latex", "pdfmd-bibliography-indent=0.5in"))
        self.assertIn("\\setlength{\\cslhangindent}{0pt}", self.out("latex", "pdfmd-bibliography-indent=0pt"))
        self.assertNotIn("cslhangindent", self.out("latex", "pdfmd-bibliography-indent-default=1.5em"))      # LaTeX has it already

    def test_typst_gets_the_indent_it_lacked(self):
        for meta in ("pdfmd-bibliography-indent=0.5in", "pdfmd-bibliography-indent-default=0.5in"):
            text = self.out("typst", meta)
            self.assertIn("#[#set par(hanging-indent: 0.5in)", text)
            self.assertEqual(text.count("hanging-indent"), 1)
        self.assertNotIn("hanging-indent", self.out("typst", "pdfmd-bibliography-indent=0pt"))
        self.assertNotIn("hanging-indent", self.out("typst"))

    def test_html_puts_it_on_each_entry_and_only_when_set(self):
        html = self.out("html", "pdfmd-bibliography-indent=0.5in")
        self.assertEqual(html.count('style="margin-left: 0.5in; text-indent: -0.5in;"'), 2)
        self.assertEqual(self.out("html", "pdfmd-bibliography-indent=0pt").count("margin-left: 0; text-indent: 0;"), 2)
        self.assertNotIn("text-indent", self.out("html", "pdfmd-bibliography-indent-default=1.5em"))

    def test_a_style_without_a_hanging_indent_is_left_alone(self):
        (self.root / "n.csl").write_text(
            '<?xml version="1.0" encoding="utf-8"?><style xmlns="http://purl.org/net/xbiblio/csl" class="in-text" version="1.0">'
            '<info><title>N</title><id>n</id><updated>2020-01-01T00:00:00+00:00</updated></info>'
            '<citation><layout><text variable="citation-number"/></layout></citation>'
            '<bibliography><layout><text variable="title"/></layout></bibliography></style>', encoding="utf-8")
        done = subprocess.run([PANDOC, "t.md", "--citeproc", "--csl", "n.csl", "-t", "html", "--lua-filter", str(LUA / "bibliography_indent.lua"),
                               "-M", "pdfmd-bibliography-indent=0.5in"], cwd=self.root, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("text-indent", done.stdout)

    def test_word_and_opendocument_name_a_paragraph_style_for_the_entries(self):
        for extension, pattern in (("docx", r'w:pStyle w:val="pdfmd-hang-0p5in"'), ("odt", r'text:style-name="pdfmd-hang-0p5in"')):
            done = self.run_pandoc(extension, "pdfmd-bibliography-indent=0.5in", output=f"o.{extension}")
            self.assertEqual(done.returncode, 0, done.stderr)
            with zipfile.ZipFile(self.root / f"o.{extension}") as archive:
                body = archive.read("word/document.xml" if extension == "docx" else "content.xml").decode("utf-8")
            self.assertEqual(len(re.findall(pattern, body)), 2, extension)
            self.assertNotIn('w:hanging="720"', body)                 # the writer's own 0.5in is not added on top


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Builds(unittest.TestCase):
    """Real builds through pdfmd."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "refs.bib").write_text(BIB, encoding="utf-8")

    def build(self, to: str, options: str = "", body: str = BODY, extra: tuple[str, ...] = (), bibliography: str = "refs.bib") -> Path:
        front = f"pdfmd-options: {{{options}}}\n" if options else ""
        named = f"bibliography: {bibliography}\n" if bibliography else ""
        (self.root / "d.md").write_text(f"---\ntitle: T\n{named}{front}---\n\n{body}", encoding="utf-8")
        out = self.root / f"out.{to}"
        out.unlink(missing_ok=True)
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", *extra, "--to", to, "-o", out.name, "--no-stamp",
                               "--no-backup", "--no-auto", "crossref"], cwd=self.root, capture_output=True, text=True,
                              env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_BUILD_LOG": "off", "PDFMD_NO_PROMPT": "1",
                                   "XDG_CACHE_HOME": str(self.root / "cache"), "LOCALAPPDATA": str(self.root / "cache")}, stdin=subprocess.DEVNULL)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return out

    def text(self, to: str, options: str = "", **kwargs) -> str:
        return self.build(to, options, **kwargs).read_text(encoding="utf-8")

    def test_typst_has_an_indent_by_default_and_zero_takes_it_away(self):
        self.assertIn("#set par(hanging-indent: 1.5em)", self.text("typ"))
        self.assertNotIn("hanging-indent: 1.5em", self.text("typ", "bibliography-indent: 0").replace("#set terms(hanging-indent: 1.5em)", ""))
        self.assertIn("#set par(hanging-indent: 0.5in)", self.text("typ", "bibliography-indent: 0.5in"))
        self.assertIn("#set par(hanging-indent: 2cm)", self.text("typ", extra=("--bibliography-indent", "2cm")))

    def test_pandocs_bibliography_option_and_the_indent_flag_together(self):
        for given in (("--bibliography", "refs.bib"), ("--bibliography=refs.bib",)):
            text = self.text("typ", extra=(*given, "--bibliography-indent", "2cm"), bibliography="")
            self.assertIn("#set par(hanging-indent: 2cm)", text, given)
            self.assertIn("(Alpha 1984; Beta 1990)", text, given)                # the file reached Pandoc: the keys resolved

    @unittest.skipUnless(shutil.which("typst") and shutil.which("pdftotext"), "needs Typst and pdftotext")
    def test_citeproc_citations_and_the_indent_build_a_typst_pdf(self):
        pdf = self.build("pdf", bibliography="", extra=("--bibliography", "refs.bib", "--bibliography-indent", "2cm",
                                                       "--engine", "typst", "--engine-fallback", "missing"))
        text = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
        self.assertIn("(Alpha 1984; Beta 1990)", text)
        self.assertIn("Second Book", text)

    def test_the_other_writers_keep_their_own_unless_it_is_set(self):
        self.assertNotIn("text-indent: -", self.text("html"))                 # the style sheet's
        self.assertNotIn("cslhangindent}{", self.text("tex").split("\\begin{document}")[-1])
        self.assertIn("margin-left: 0.5in; text-indent: -0.5in;", self.text("html", "bibliography-indent: 0.5in"))
        self.assertIn("\\setlength{\\cslhangindent}{0.5in}", self.text("tex", "bibliography-indent: 0.5in"))

    def test_word_and_opendocument_get_the_style_written_in(self):
        docx = self.build("docx", "bibliography-indent: 0.5in")
        with zipfile.ZipFile(docx) as archive:
            styles = archive.read("word/styles.xml").decode("utf-8")
        found = re.search(r'<w:style [^>]*w:styleId="pdfmd-hang-0p5in".*?</w:style>', styles, re.S)
        self.assertIsNotNone(found)
        self.assertIn('<w:ind w:left="720" w:hanging="720"/>', found.group(0))
        odt = self.build("odt", "bibliography-indent: 0.5in")
        with zipfile.ZipFile(odt) as archive:
            styles = archive.read("styles.xml").decode("utf-8")
        # LibreOffice (the route of an .odt when it is installed) writes 1.27cm, Pandoc's own route 0.5000in
        self.assertRegex(styles, r'style:name="pdfmd-hang-0p5in".*?fo:margin-left="(?:0.5000in|1.27cm)" fo:text-indent="-(?:0.5000in|1.27cm)"')

    def test_fullcite_entries_take_the_same_value(self):
        body = "[@a]{.fullcite}\n"
        self.assertIn("\\hangindent=0.5in\\hangafter=1", self.text("tex", "bibliography-indent: 0.5in", body=body))
        self.assertIn("\\hangindent=1.5em\\hangafter=1", self.text("tex", body=body))                      # the default
        self.assertNotIn("hangindent", self.text("tex", "bibliography-indent: 0", body=body))
        self.assertIn("#par(hanging-indent: 0.5in)[", self.text("typ", "bibliography-indent: 0.5in", body=body))
        docx = self.build("docx", "bibliography-indent: 0.5in", body=body)
        with zipfile.ZipFile(docx) as archive:
            self.assertIn('w:val="pdfmd-hang-0p5in"', archive.read("word/document.xml").decode("utf-8"))

@unittest.skipUnless(PANDOC, "needs Pandoc")
class CSLLineSpacing(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="pdfmd-csl-line-spacing-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        (self.root / "refs.bib").write_text(BIB, encoding="utf-8")

    def build(self, writer, spacing="2", bypass=False, options=""):
        attrs = ' line-spacing="' + spacing + '"' if spacing else ""
        style = ('<style xmlns="http://purl.org/net/xbiblio/csl" class="in-text" version="1.0">'
                 '<info><title>Spacing</title><id>spacing</id></info>'
                 '<citation><layout><text variable="title"/></layout></citation>'
                 '<bibliography entry-spacing="1" hanging-indent="true"' + attrs + '>'
                 '<layout><text variable="title"/></layout></bibliography></style>')
        (self.root / "style.csl").write_text(style, encoding="utf-8")
        source = self.root / "doc.md"
        source.write_text("---\ntitle: Spacing\nbibliography: refs.bib\ncsl: style.csl\n"
                          + options + "---\n\nBefore.\n\n" + BODY + "\nAfter.\n", encoding="utf-8")
        output = self.root / ("doc." + writer)
        launch = [sys.executable, str(ROOT / "scripts/pdfmd")]
        if bypass:
            # Compare the complete pipeline with just the new fallback disabled.
            code = ("import sys; sys.path.insert(0, " + repr(str(ROOT)) + "); import pdfmd\n"
                    "original = pdfmd.bibliography_indent_args\n"
                    "def args(*a, **kw):\n"
                    "    result = original(*a, **kw)\n"
                    "    return [word for i, word in enumerate(result) if not "
                    "(word.endswith('bibliography_spacing.lua') or "
                    "(word == '--lua-filter' and i + 1 < len(result) and "
                    "result[i + 1].endswith('bibliography_spacing.lua')))]\n"
                    "pdfmd.bibliography_indent_args = args\n"
                    "pdfmd.main()\n")
            launch = [sys.executable, "-c", code]
        done = subprocess.run([*launch, str(source), "-t", writer, "-s", "-o", str(output),
                               "--no-stamp", "--no-backup"], cwd=self.root, capture_output=True, text=True,
                              encoding="utf-8", env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                                                    "SOURCE_DATE_EPOCH": "1577836800"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        if writer == "docx":
            with zipfile.ZipFile(output) as archive:
                return {name: archive.read(name) for name in archive.namelist()}
        return output.read_bytes()

    def test_double_spaced_bibliography_in_each_writer(self):
        for writer in ("latex", "typst", "html", "docx"):
            with self.subTest(writer=writer):
                out = self.build(writer)
                if writer == "docx":
                    from xml.etree import ElementTree as ET
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    root = ET.fromstring(out["word/document.xml"])
                    entries = [p for p in root.findall(".//w:p", ns)
                               if "book" in "".join(p.itertext()).lower() and
                               p.find("w:pPr/w:pStyle", ns) is not None and
                               p.find("w:pPr/w:pStyle", ns).get("{" + ns["w"] + "}val") == "Bibliography"]
                    self.assertEqual(len(entries), 2)
                    for entry in entries:
                        spacing = entry.find("w:pPr/w:spacing", ns)
                        self.assertIsNotNone(spacing)
                        self.assertEqual(spacing.get("{" + ns["w"] + "}line"), "480")
                    self.assertNotIn(b"pdfmd-csl-line-spacing", out["word/document.xml"])
                else:
                    text = out.decode("utf-8")
                    if writer == "latex":
                        self.assertIn("\\begingroup\\linespread{2}\\selectfont", text)
                        self.assertLess(text.index("\\linespread{2}"), text.index("\\begin{CSLReferences}"))
                        self.assertIn("\\par\\endgroup", text)
                    elif writer == "html":
                        self.assertRegex(text, r'id="refs"[^>]*style="line-height: 2;"')
                    else:
                        self.assertIn("#[ // pdfmd CSL line-spacing", text)
                        self.assertIn("#set par(leading: 1.7635em)", text)

    def test_without_attribute_is_byte_identical(self):
        for writer in ("latex", "typst", "html", "docx"):
            with self.subTest(writer=writer):
                normal = self.build(writer, spacing="")
                before = (self.root / ("doc." + writer)).read_bytes()
                self.assertEqual(normal, self.build(writer, spacing="", bypass=True))
                self.assertEqual(before, (self.root / ("doc." + writer)).read_bytes())

    @unittest.skipUnless(shutil.which("typst") and shutil.which("pdftotext"), "needs Typst and pdftotext")
    def test_typst_line_pitch_doubles_inside_the_bibliography_only(self):
        words = " ".join(["word"] * 65)
        (self.root / "refs.bib").write_text(
            "@book{a, title={Entry " + words + "}, year={2020}}\n"
            "@book{b, title={Second entry}, year={2021}}\n", encoding="utf-8")
        for mode in ("latex", "pandoc"):
            pitches = []
            for lines in ("1", "2"):
                typ = self.root / "render.typ"
                typ.write_bytes(self.build("typst", spacing=lines, options="mainfont: Libertinus Serif\nlinestretch: 1.5\npdfmd-options: {typst-line-spacing: " + mode + "}\n"))
                # Add two body lines after the closed bibliography scope.
                with typ.open("a", encoding="utf-8") as output:
                    output.write("\nOutsideone\\\nOutsidetwo\n")
                pdf = self.root / "render.pdf"
                done = subprocess.run(["typst", "compile", str(typ), str(pdf)], cwd=self.root,
                                      capture_output=True, text=True, encoding="utf-8", env={**os.environ})
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                xml = subprocess.run(["pdftotext", "-bbox-layout", str(pdf), "-"], capture_output=True,
                                     text=True, encoding="utf-8", check=True).stdout
                layout = [(float(top), word) for top, word in re.findall(
                    r'<line xMin="[^"]+" yMin="([^"]+)".*?<word[^>]*>([^<]*)', xml, re.S)]
                start = next(i for i, (_, word) in enumerate(layout) if word == "Entry")
                outside = next(i for i, (_, word) in enumerate(layout) if word == "Outsideone")
                pitches.append((layout[start + 1][0] - layout[start][0], layout[outside + 1][0] - layout[outside][0]))
            self.assertAlmostEqual(pitches[1][0], 2 * pitches[0][0], delta=0.2)
            self.assertAlmostEqual(pitches[1][1], pitches[0][1], delta=0.2)

    def test_word_native_spacing_is_retained(self):
        native = self.build("docx", bypass=True)
        if b'w:line="480"' not in native["word/document.xml"]:
            self.skipTest("this Pandoc needs the Word line-spacing fallback")
        self.assertEqual(self.build("docx"), native)

    def test_word_hanging_indent_override_and_spacing_coexist(self):
        out = self.build("docx", options="pdfmd-options: {bibliography-indent: 0.5in}\n")
        document = out["word/document.xml"].decode("utf-8")
        self.assertEqual(document.count('w:val="pdfmd-hang-0p5in"'), 2)
        self.assertEqual(document.count('w:line="480"'), 2)
        self.assertIn(b'w:hanging="720"', out["word/styles.xml"])


if __name__ == "__main__":
    unittest.main()
