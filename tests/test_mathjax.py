"""v3.28.46: MathJax typesets the math of a WeasyPrint PDF first, KaTeX takes what MathJax cannot read, the rest stays text.

The install (`pdfmd --install math:mathjax`), the font that goes with the body font, the variables pdfmd gives the filter,
the filter itself (with stand-ins for node, so it needs only Pandoc) and, where MathJax is installed here, a real build."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

LUA = ROOT / "pdfmd_lua" / "weasyprint.lua"
PANDOC = shutil.which("pandoc")
JAX = pdfmd.mathjax_runtime()                                  # the MathJax this machine has, for the real build


def tarball(path: Path, names: list[str]) -> Path:
    with tarfile.open(path, "w:gz") as bundle:
        for name in names:
            member = tarfile.TarInfo(name)
            data = name.encode()
            member.size = len(data)
            bundle.addfile(member, io.BytesIO(data))
    return path


class Install(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-mathjax-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def fetcher(self, calls: list):
        def fetch(url, destination, sha256):
            calls.append((url, sha256))
            if "/src/" in url:
                names = ["package/package.json", "package/LICENSE", "package/bundle/node-main.cjs", "package/bundle/package.json",
                         "package/bundle/core.js", "package/bundle/input/tex.js", "package/bundle/input/tex-base.js",
                         "package/bundle/input/tex/extensions/ams.js", "package/bundle/adaptors/liteDOM.js",
                         "package/bundle/output/chtml.js", "package/bundle/output/svg.js", "package/bundle/a11y/explorer.js",
                         "package/bundle/sre/sre.js", "package/bundle/tex-chtml.js", "package/mjs/core/Tree.js",
                         "package/bundle/input/mml.js", "../escape.js"]
            else:
                names = ["package/package.json", "package/chtml.js", "package/chtml/woff2/mjx-stx-n.woff2",
                         "package/chtml/dynamic/arrows.js", "package/svg.js", "package/cjs/x.js",
                         "package/tex-mml-chtml-mathjax-stix2.js"]
            tarball(destination, names)
        return fetch

    def files(self, folder: Path) -> list[str]:
        return sorted(item.relative_to(folder).as_posix() for item in folder.rglob("*") if item.is_file())

    def test_only_what_pdfmd_runs_is_kept_from_each_package(self):
        calls: list = []
        target = self.directory / "mathjax" / "4.1.3"
        pdfmd.install_mathjax_files(target, ("stix2",), self.fetcher(calls))
        source = self.files(target / "node_modules" / "@mathjax" / "src")
        self.assertEqual(source, ["LICENSE", "bundle/adaptors/liteDOM.js", "bundle/core.js", "bundle/input/tex-base.js",
                                  "bundle/input/tex.js", "bundle/input/tex/extensions/ams.js", "bundle/node-main.cjs",
                                  "bundle/output/chtml.js", "bundle/package.json", "package.json"])
        font = self.files(target / "node_modules" / "@mathjax" / "mathjax-stix2-font")
        self.assertEqual(font, ["chtml.js", "chtml/dynamic/arrows.js", "chtml/woff2/mjx-stx-n.woff2", "package.json"])
        self.assertFalse((self.directory / "escape.js").exists())                  # nothing outside the package
        self.assertFalse((target.with_name("4.1.3.part")).exists())

    def test_every_archive_is_checked_against_its_pinned_sha256(self):
        calls: list = []
        with mock.patch.dict(pdfmd.MATHJAX_FONT_SHA256, {"termes": "7" * 64}):
            pdfmd.install_mathjax_files(self.directory / "m", ("stix2", "termes"), self.fetcher(calls))
        self.assertEqual([item[1] for item in calls], [pdfmd.MATHJAX_SOURCE_SHA256, pdfmd.MATHJAX_FONT_SHA256["stix2"],
                                                       "7" * 64])
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", item[1]) for item in calls))
        self.assertEqual(calls[0][0], "https://registry.npmjs.org/@mathjax/src/-/src-4.1.3.tgz")
        self.assertEqual(calls[1][0], "https://registry.npmjs.org/@mathjax/mathjax-stix2-font/-/mathjax-stix2-font-4.1.3.tgz")

    def test_a_font_added_later_leaves_the_ones_there(self):
        calls: list = []
        target = self.directory / "m"
        pdfmd.install_mathjax_files(target, ("stix2",), self.fetcher(calls))
        calls.clear()
        with mock.patch.dict(pdfmd.MATHJAX_FONT_SHA256, {"pagella": "9" * 64}):
            pdfmd.install_mathjax_files(target, ("stix2", "pagella"), self.fetcher(calls))
            self.assertEqual([item[0].rsplit("/", 1)[1] for item in calls],
                             ["src-4.1.3.tgz", "mathjax-pagella-font-4.1.3.tgz"])    # stix2 was there: not fetched again
            self.assertEqual(pdfmd.mathjax_fonts(target), ["stix2", "pagella"])

    def test_a_package_with_nothing_pdfmd_needs_is_an_error(self):
        def fetch(url, destination, sha256):
            tarball(destination, ["package/README.md"])
        with self.assertRaises(OSError):
            pdfmd.install_mathjax_files(self.directory / "m", ("stix2",), fetch)

    def test_the_folder_is_this_releases_or_the_newest_other_one_with_a_font(self):
        root = self.directory / "data" / "mathjax"
        with mock.patch.object(pdfmd, "data_root", return_value=self.directory / "data"):
            self.assertIsNone(pdfmd.mathjax_folder())
            for version in ("4.0.0", "4.1.3", "3.9.0"):
                pdfmd.install_mathjax_files(root / version, ("stix2",), self.fetcher([]))
            self.assertEqual(pdfmd.mathjax_folder(), root / pdfmd.MATHJAX_VERSION)
            shutil.rmtree(root / pdfmd.MATHJAX_VERSION)
            self.assertEqual(pdfmd.mathjax_folder(), root / "4.0.0")
            shutil.rmtree(root / "4.0.0" / "node_modules" / "@mathjax" / "mathjax-stix2-font")
            self.assertEqual(pdfmd.mathjax_folder(), root / "3.9.0")                  # a folder with no font is not usable
            with mock.patch.object(pdfmd, "which", return_value=None):
                self.assertIsNone(pdfmd.mathjax_runtime())                            # MathJax without node: nothing

    def test_the_kind_is_math_mathjax_and_nothing_longer(self):
        self.assertEqual(pdfmd.install_kind("math:mathjax"), "math:mathjax")
        for bad in ("math:mathjax:", "math:mathjax:newcm", "math:mathjaxx"):
            with self.assertRaises(Exception, msg=bad):
                pdfmd.install_kind(bad)
        self.assertEqual(pdfmd.install_kind("math:katex"), "math:katex")

    def test_the_pinned_names_are_the_ones_the_table_uses(self):
        self.assertEqual(set(pdfmd.MATHJAX_FONT_FOR.values()) | {pdfmd.MATHJAX_DEFAULT_FONT}, set(pdfmd.MATHJAX_FONT_SHA256))
        self.assertEqual(set(pdfmd.MATHJAX_FONT_SIZES), set(pdfmd.MATHJAX_FONT_SHA256))


class FontChoice(unittest.TestCase):
    def test_the_font_that_goes_with_the_body_when_it_is_installed(self):
        self.assertEqual(pdfmd.mathjax_font_for("STIX Two Text", ["stix2"]), ("stix2", True))
        self.assertEqual(pdfmd.mathjax_font_for("stix two text", ["stix2"]), ("stix2", True))
        with mock.patch.dict(pdfmd.MATHJAX_FONT_FOR, {"tex gyre termes": "termes"}):        # the table's shape, for a later font
            self.assertEqual(pdfmd.mathjax_font_for("TeX Gyre Termes", ["stix2", "termes"]), ("termes", True))
            self.assertEqual(pdfmd.mathjax_font_for("TeX Gyre Termes", ["stix2"]), ("stix2", False))    # not installed

    def test_another_body_gets_stix_two_scaled_and_a_missing_font_falls_back(self):
        self.assertEqual(pdfmd.mathjax_font_for("Georgia", ["stix2"]), ("stix2", False))
        self.assertEqual(pdfmd.mathjax_font_for(None, ["stix2"]), ("stix2", False))
        self.assertEqual(pdfmd.mathjax_font_for("Georgia", ["newcm"]), ("newcm", False))              # the only one there
        self.assertIsNone(pdfmd.mathjax_font_for("STIX Two Text", []))


class Arguments(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="pdfmd-mathjax-args-"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def args(self, body="STIX Two Text", options=None, no_auto=None, jax=True, katex=True, fonts=("stix2",), height=0.459):
        runtime = ("/opt/node/bin/node", self.folder) if jax else None
        with mock.patch.object(pdfmd, "mathjax_runtime", return_value=runtime), \
                mock.patch.object(pdfmd, "mathjax_fonts", return_value=list(fonts)), \
                mock.patch.object(pdfmd, "katex_runtime", return_value=("/opt/node/bin/node", self.folder) if katex else None), \
                mock.patch.object(pdfmd, "katex_scale", return_value=1.07), \
                mock.patch.object(pdfmd, "body_x_height", return_value=height):
            return pdfmd.weasyprint_math_args("weasyprint", options or [], body, no_auto)

    def test_the_filter_is_told_the_folder_the_font_and_node(self):
        arguments = self.args()
        self.assertIn(f"pdfmd-mathjax={self.folder}", arguments)
        self.assertIn("pdfmd-mathjax-font=stix2", arguments)
        self.assertIn("pdfmd-mathjax-node=/opt/node/bin/node", arguments)
        self.assertIn(f"pdfmd-katex={self.folder}", arguments)                   # KaTeX stays behind it
        self.assertEqual(arguments[-2:], ["--lua-filter", str(LUA)])

    def test_the_size_match_is_asked_for_only_when_the_font_is_not_made_for_the_body(self):
        self.assertFalse([item for item in self.args() if item.startswith("pdfmd-body-xheight")])
        odd = self.args(body="Georgia", height=0.4781)
        self.assertIn("pdfmd-body-xheight=0.4781", odd)
        self.assertIn("pdfmd-mathjax-font=stix2", odd)
        self.assertFalse([item for item in self.args(body="Georgia", height=None) if item.startswith("pdfmd-body-xheight")])

    def test_no_auto_mathjax_leaves_the_math_to_katex(self):
        arguments = self.args(no_auto=["mathjax"])
        self.assertFalse([item for item in arguments if item.startswith("pdfmd-mathjax")])
        self.assertIn(f"pdfmd-katex={self.folder}", arguments)

    def test_the_command_lines_math_wins_over_both(self):
        arguments = self.args(options=["--mathml"])
        self.assertFalse([item for item in arguments if item.startswith(("pdfmd-mathjax", "pdfmd-katex"))])

    def test_nothing_is_set_when_mathjax_or_its_font_is_missing(self):
        self.assertFalse([item for item in self.args(jax=False) if item.startswith("pdfmd-mathjax")])
        self.assertFalse([item for item in self.args(fonts=()) if item.startswith("pdfmd-mathjax")])
        self.assertEqual(self.args(jax=False, katex=False)[-2:], ["--lua-filter", str(LUA)])

    def test_only_weasyprint_has_them(self):
        self.assertEqual(pdfmd.weasyprint_math_args("typst", []), [])


STUB = """#!{python}
import json, sys
request = json.load(sys.stdin)
script = sys.argv[1]
mode = {mode!r}
engine = "mj" if "mathjax" in script else "kx"
def good(item):
    return {{"html": "<span class=\\"" + engine + "\\">" + item["tex"] + "</span>"}}
if engine == "mj":
    if mode["jax"] == "crash":
        sys.stderr.write("node: boom")
        sys.exit(1)
    answers = [{{"error": "Undefined control sequence " + item["tex"]}} if item["tex"] in mode["jax_bad"] else good(item)
               for item in request["items"]]
    json.dump({{"css": "/* mathjax css */", "xheight": 0.479, "answers": answers}}, sys.stdout)
else:
    answers = [{{"error": "KaTeX parse error: Undefined control sequence: " + item["tex"] + " at position 1: x"}}
               if item["tex"] in mode["katex_bad"] else good(item) for item in request["items"]]
    json.dump(answers, sys.stdout)
"""


@unittest.skipUnless(PANDOC and sys.platform != "win32", "needs Pandoc and a POSIX shell for the stand-in node")
class Filter(unittest.TestCase):
    """pdfmd_lua/weasyprint.lua with a stand-in for node: what it asks, what it puts in the page, what it says."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-mathjax-filter-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def run_filter(self, text: str, *, jax=True, katex=True, jax_mode="ok", jax_bad=(), katex_bad=(), body_xheight=None,
                   standalone=False):
        stub = self.directory / "node"
        stub.write_text(STUB.format(python=sys.executable, mode={"jax": jax_mode, "jax_bad": list(jax_bad),
                                                                 "katex_bad": list(katex_bad)}), encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        command = [PANDOC, "-f", "markdown", "-t", "html", "--math-method=plain" if pdfmd.pandoc_has_option("--math-method")
                   else "--webtex", "--lua-filter", str(LUA)]
        if standalone:
            command.append("-s")
        if jax:
            command += ["-V", f"pdfmd-mathjax={self.directory}", "-V", "pdfmd-mathjax-font=stix2",
                        "-V", f"pdfmd-mathjax-node={stub}"]
        if katex:
            command += ["-V", f"pdfmd-katex={self.directory}", "-V", f"pdfmd-katex-url={self.directory.as_uri()}",
                        "-V", f"pdfmd-katex-node={stub}"]
        if body_xheight:
            command += ["-V", f"pdfmd-body-xheight={body_xheight}"]
        done = subprocess.run(command, input=text, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout, done.stderr

    def test_mathjax_typesets_everything_and_the_page_gets_its_style_and_the_fixes(self):
        out, said = self.run_filter("A $x^2$ and $$y$$ and $x^2$ again.\n")
        self.assertEqual(out.count('<span class="mj">'), 3)
        self.assertNotIn('class="kx"', out)
        self.assertNotIn("katex.min.css", out)                                    # KaTeX was not needed: not linked
        self.assertIn("/* mathjax css */", out)
        for rule in ("mjx-c { margin-top: -0.29em; }", "mjx-stretchy-h > mjx-ext { overflow: hidden; }",
                     "mjx-under > mjx-mo > mjx-box"):
            self.assertIn(rule, out)
        self.assertEqual(said, "")

    def test_what_mathjax_cannot_read_goes_to_katex_and_is_said_once(self):
        out, said = self.run_filter("Good $x$, odd $\\a$, and $\\a$ again.\n", jax_bad=["\\a"])
        self.assertEqual(out.count('<span class="mj">'), 1)
        self.assertEqual(out.count('<span class="kx">'), 2)
        self.assertIn("katex.min.css", out)
        self.assertEqual(said.count("NOTE  weasyprint: MathJax could not typeset 2 of 3 formulas, KaTeX did"), 1, said)
        self.assertIn("Undefined control sequence", said)
        self.assertNotIn("WARN", said)

    def test_what_neither_reads_stays_text_with_one_warning_naming_both(self):
        out, said = self.run_filter("Good $x$, bad $\\a$.\n", jax_bad=["\\a"], katex_bad=["\\a"])
        self.assertEqual(said.count("WARN  weasyprint: MathJax and KaTeX could not typeset 1 of 2 formulas"), 1, said)
        self.assertIn('<span class="mj">', out)
        self.assertIn("\\a", out)

    def test_mathjax_alone_names_itself_in_the_warning(self):
        out, said = self.run_filter("Good $x$, bad $\\a$.\n", katex=False, jax_bad=["\\a"])
        self.assertIn("WARN  weasyprint: MathJax could not typeset 1 of 2 formulas, printed as text", said)
        self.assertNotIn("KaTeX", said)

    def test_katex_alone_is_what_it_was(self):
        out, said = self.run_filter("Good $x$, bad $\\a$.\n", jax=False, katex_bad=["\\a"])
        self.assertIn("WARN  weasyprint: KaTeX could not typeset 1 of 2 formulas, printed as text", said)
        self.assertNotIn("mjx", out)
        self.assertIn('<span class="kx">', out)

    def test_node_failing_for_mathjax_hands_everything_to_katex(self):
        out, said = self.run_filter("A $x$ and $y$.\n", jax_mode="crash")
        self.assertEqual(out.count('<span class="kx">'), 2)
        self.assertIn("WARN  weasyprint: MathJax could not run (", said)
        self.assertIn("; KaTeX typesets the formulas", said)

    def test_neither_engine_asked_for_is_the_old_warning(self):
        out, said = self.run_filter("A $x$.\n", jax=False, katex=False)
        self.assertIn("WeasyPrint does not typeset math", said)
        self.assertIn("pdfmd --install math:mathjax", said)
        self.assertIn("pdfmd --install math:katex", said)

    def test_the_size_match_for_a_body_the_font_is_not_made_for(self):
        plain, _ = self.run_filter("$x$\n")
        self.assertNotIn("font-size:", plain.split("mathjax css")[1].split("</style>")[0])
        out, _ = self.run_filter("$x$\n", body_xheight=0.5)
        self.assertIn('mjx-container[jax="CHTML"] mjx-math { font-size: 104%; }', out)      # 0.5 / 0.479
        huge, _ = self.run_filter("$x$\n", body_xheight=0.9)
        self.assertIn("font-size: 140%;", huge)                                              # kept within 0.85 and 1.4

    def test_a_title_with_a_formula_keeps_its_plain_text_for_the_pdfs_title(self):
        out, _ = self.run_filter("---\ntitle: Energy $E = mc^2$ here\n---\n\nWords.\n", standalone=True)
        self.assertIn("<title>Energy E = mc^2 here</title>", out)


@unittest.skipUnless(PANDOC and JAX and shutil.which("weasyprint") and shutil.which("pdftotext"),
                     "needs Pandoc, WeasyPrint, Poppler and `pdfmd --install math:mathjax`")
class Real(unittest.TestCase):
    """The installed MathJax through the whole of pdfmd."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-mathjax-real-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def build(self, text: str, *extra: str) -> subprocess.CompletedProcess:
        (self.directory / "doc.md").write_text(text, encoding="utf-8")
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "doc.md", "-e", "weasyprint", "--no-stamp", *extra],
                              capture_output=True, text=True, encoding="utf-8", cwd=self.directory,
                              env={**os.environ, "PDFMD_NO_PROMPT": "1"})

    def words(self) -> list[tuple[str, float, float]]:
        out = subprocess.run(["pdftotext", "-bbox", str(self.directory / "doc.pdf"), "-"], capture_output=True, text=True).stdout
        return [(match.group(4), float(match.group(1)), float(match.group(2)))
                for match in re.finditer(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="[\d.]+">([^<]*)</word>', out)]

    def test_math_is_typeset_in_mathjaxs_font_without_a_word_said(self):
        done = self.build("---\ntitle: J\n---\n\nSee $\\frac{a}{b} \\neq \\vec{v}$ and\n\n$$\\sum_{n=1}^{\\infty} \\frac{1}{n^2}$$\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        said = done.stdout + done.stderr
        self.assertNotIn("typeset math", said)
        self.assertNotIn("could not", said)
        self.assertNotIn("WARNING: Ignored", said)
        fonts = subprocess.run(["pdffonts", str(self.directory / "doc.pdf")], capture_output=True, text=True).stdout
        self.assertIn("MJX-STX", fonts)
        self.assertNotIn("\\frac", subprocess.run(["pdftotext", str(self.directory / "doc.pdf"), "-"], capture_output=True,
                                                  text=True).stdout)

    def test_an_accent_sits_on_its_letter_not_three_points_over_it(self):
        # WeasyPrint took each glyph box 0.262em too tall: a hat floated ~3.4pt higher than it should (v3.28.46)
        done = self.build("---\ntitle: J\n---\n\n$\\hat{x}$\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        letter = next(item for item in self.words() if item[0] == "\U0001d465")
        accent = next(item for item in self.words() if item[0] == "\u02c6")
        self.assertLess(abs(accent[2] - letter[2]), 1.5, (letter, accent))

    def test_a_formula_neither_engine_reads_is_text(self):
        done = self.build("---\ntitle: J\n---\n\nGood $x^2$, bad $\\nosuchmacro{y}$.\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("could not typeset 1 of 2 formulas", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
