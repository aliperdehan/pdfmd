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
            self.assertEqual(args(document, [], ["--citeproc"], [], "latex"), [])         # nothing set: the writer's own
            self.assertEqual(args(document, [], ["--citeproc"], [], "docx"), [])
            typst = args(document, [], ["--citeproc"], [], "typst")
            self.assertEqual(typst, ["-M", "pdfmd-bibliography-indent-default=1.5em", "--lua-filter", str(LUA / "bibliography_indent.lua")])
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


if __name__ == "__main__":
    unittest.main()
