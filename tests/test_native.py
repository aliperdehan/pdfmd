"""Tests for the native tier (v3.20.0): the vendored inkmd, the GFM normaliser,
engine selection without Pandoc, and a real `pdfmd` run with nothing on PATH.

    python3 -m unittest discover -s tests -v

PDFMD_GOLDEN=1 additionally compares the vendored inkmd's output with the
SHA-256 files in tests/golden (run it after re-vendoring: any difference is
a change in upstream's output to look at). PDFMD_GOLDEN=update rewrites them.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# never read or write the real user's config and state while testing
import os as _os, tempfile as _tempfile  # noqa: E402
_os.environ["PDFMD_CONFIG"] = ""
_os.environ["XDG_CONFIG_HOME"] = _tempfile.mkdtemp(prefix="pdfmd-test-config-")

import pdfmd  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN = ROOT / "tests" / "golden"

try:
    import pypdf
except ImportError:  # pragma: no cover
    pypdf = None


def compile_gfm(name: str) -> bytes:
    import pdfmd_inkmd
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pdfmd_inkmd.compile((FIXTURES / name).read_text(encoding="utf-8"), page_size="a4")


class VendoredInkmdTests(unittest.TestCase):
    def test_imports_under_its_own_name(self):
        import pdfmd_inkmd
        self.assertTrue(hasattr(pdfmd_inkmd, "compile"))
        package = Path(pdfmd_inkmd.__file__).parent
        for path in package.glob("*.py"):
            for line in path.read_text(encoding="utf-8").splitlines():
                self.assertFalse(line.lstrip().startswith(("from inkmd", "import inkmd")),
                                 f"{path.name}: {line}")

    def test_ships_without_the_emoji_font(self):
        import pdfmd_inkmd
        package = Path(pdfmd_inkmd.__file__).parent
        self.assertFalse((package / "assets" / "emoji").exists())
        self.assertTrue((package / "assets" / "fonts" / "DejaVuSans.ttf").is_file())
        self.assertTrue((package / "LICENSE").is_file())

    def test_output_is_deterministic(self):
        first = compile_gfm("gfm.md")
        self.assertTrue(first.startswith(b"%PDF-"))
        self.assertEqual(first, compile_gfm("gfm.md"))

    @unittest.skipUnless(os.environ.get("PDFMD_GOLDEN"), "set PDFMD_GOLDEN=1 (or =update) to compare goldens")
    def test_golden_output(self):
        digest = hashlib.sha256(compile_gfm("gfm.md")).hexdigest()
        golden = GOLDEN / "gfm.sha256"
        if os.environ["PDFMD_GOLDEN"] == "update":
            golden.write_text(digest + "\n", encoding="utf-8")
        self.assertEqual(digest, golden.read_text(encoding="utf-8").strip())


class NormaliseTests(unittest.TestCase):
    def normalise(self, text: str, engine: str = "inkmd"):
        return pdfmd.normalise_gfm(text, engine)

    def test_heading_and_image_attributes_removed(self):
        source, counts = self.normalise("# Title {#id .class}\n\n![alt](a.png){width=50%}\n")
        self.assertIn("# Title\n", source.text)
        self.assertIn("![alt](a.png)\n", source.text)
        self.assertEqual(counts["attributes"], 2)

    def test_fenced_code_is_untouched(self):
        text = "```\n# Heading {#keep}\n::: div\n\\newpage\n$x$\n```\n"
        source, counts = self.normalise(text)
        self.assertIn("# Heading {#keep}", source.text)
        self.assertIn("::: div", source.text)
        self.assertIn("\\newpage", source.text)
        self.assertEqual(counts, {})

    def test_fenced_div_markers_removed_content_kept(self):
        source, counts = self.normalise("::: {.note}\nInside.\n:::\n")
        self.assertEqual(source.text.strip(), "Inside.")
        self.assertEqual(counts["divs"], 2)

    def test_raw_latex_removed(self):
        text = "Before\n\n\\vspace{1cm}\n\n```{=latex}\n\\clearpage\n```\n\n\\begin{tikzpicture}\nx\n\\end{tikzpicture}\n\nAfter\n"
        source, counts = self.normalise(text)
        self.assertNotIn("tikz", source.text)
        self.assertNotIn("vspace", source.text)
        self.assertNotIn("clearpage", source.text)
        self.assertIn("Before", source.text)
        self.assertIn("After", source.text)
        self.assertEqual(counts["latex"], 3)

    def test_math_environments_become_display_math(self):
        source, counts = self.normalise("\\begin{equation} a = b \\end{equation}\n")
        self.assertNotIn("begin{equation}", source.text)
        self.assertIn("*a* = *b*", source.text)
        self.assertEqual(counts["math"], 1)
        self.assertEqual(counts["math_text"], 1)

    def test_csv_div_is_still_detected_on_the_pandoc_route(self):
        # The native tier once redefined CSV_DIV_RE, silently disabling the
        # Pandoc route's CSV filter for any file with the div past its first line.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "t.md"
            path.write_text('# T\n\nText.\n\n::: {.csv file="data.csv"}\n:::\n', encoding="utf-8")
            self.assertTrue(pdfmd.contains_csv_table(path))
            path.write_text("# T\n\nNo table.\n", encoding="utf-8")
            self.assertFalse(pdfmd.contains_csv_table(path))

    def test_csv_div_becomes_a_table_like_the_pandoc_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = "\n".join(f"{n},{n * n},x|y" for n in range(1, 13))
            (Path(directory) / "data.csv").write_text("n,square,text\n" + rows + "\n", encoding="utf-8")
            source, counts = pdfmd.normalise_gfm('A\n\n::: {.csv file="data.csv"}\n:::\n\nB\n', "inkmd",
                                                 base_dir=Path(directory))
            self.assertEqual(counts["csv"], 1)
            self.assertIn("| n | square | text |\n| --- | --- | --- |\n| 1 | 1 | x\\|y |", source.text)
            self.assertIn("| 10 | 100 |", source.text)
            self.assertNotIn("| 11 |", source.text)
            self.assertIn("showing 10 of 12 rows, 3 of 3 columns", source.text)
            full, _ = pdfmd.normalise_gfm('::: {.csv file="data.csv" rows=all header="false"}\n:::\n', "inkmd",
                                          base_dir=Path(directory))
            self.assertIn("| Column 1 | Column 2 | Column 3 |", full.text)
            self.assertIn("| n | square | text |", full.text)
            self.assertIn("| 12 | 144 |", full.text)

    def test_html_comments_are_dropped_outside_code(self):
        text = ("Before <!-- inline --> after.\n\n<!--\nmulti\nline -->\n\nKept `<!-- code -->` here.\n\n"
                "```\n<!-- fenced -->\n```\n")
        source, _ = self.normalise(text)
        self.assertIn("Before  after.", source.text)
        self.assertNotIn("inline", source.text)
        self.assertNotIn("multi", source.text)
        self.assertIn("`<!-- code -->`", source.text)
        self.assertIn("<!-- fenced -->", source.text)

    def test_pagebreak_comment_is_a_page_break(self):
        self.assertIn("page-break-after", self.normalise("A\n\n<!-- pagebreak -->\n\nB\n", "inkmd")[0].text)
        self.assertIn("\\pagebreak", self.normalise("A\n\n<!--PageBreak-->\n\nB\n", "md2pdf")[0].text)

    def test_page_break_per_engine(self):
        self.assertIn("page-break-after", self.normalise("\\newpage\n", "inkmd")[0].text)
        self.assertIn("\\pagebreak", self.normalise("\\newpage\n", "md2pdf")[0].text)

    def test_footnotes_become_endnotes_for_inkmd_only(self):
        text = "Text[^a] and again[^a], plus[^b].\n\n[^a]: First\n    continued\n[^b]: Second\n"
        source, counts = self.normalise(text, "inkmd")
        self.assertIn("Text<sup>1</sup> and again<sup>1</sup>, plus<sup>2</sup>.", source.text)
        self.assertIn("1. First continued", source.text)
        self.assertIn("2. Second", source.text)
        self.assertEqual(counts["footnotes"], 2)
        kept, _ = self.normalise(text, "md2pdf")
        self.assertIn("[^a]: First", kept.text)
        self.assertTrue(kept.has_footnotes)

    def test_math_and_citations_are_counted_not_currency_or_code(self):
        text = "Costs $5 and $6 today. `$code$` stays. Real $x^2$ and\n\n$$\ny = 1\n$$\n\nSee [@a] and [-@b].\n"
        source, counts = self.normalise(text)
        self.assertEqual(counts["math"], 2)
        self.assertEqual(counts["citations"], 2)
        self.assertEqual(source.math, 2)

    def test_title_block_and_metadata(self):
        text = (FIXTURES / "pandoc.md").read_text(encoding="utf-8")
        source, _ = self.normalise(text)
        self.assertTrue(source.text.startswith("# Pandoc-flavoured\n\n*Ada Example, Bob Example"))
        self.assertEqual(pdfmd.ignored_front_matter_keys(source.metadata),
                         ["documentclass", "header-includes", "pdfmd-options"])
        self.assertEqual(pdfmd.author_names(source.metadata["author"]), ["Ada Example", "Bob Example"])

    def test_no_duplicate_title_when_body_starts_with_it(self):
        source, _ = self.normalise("---\ntitle: Same\n---\n\n# Same\n\nBody\n")
        self.assertEqual(source.text.count("# Same"), 1)

    def test_md2pdf_gets_minimal_front_matter(self):
        source, _ = self.normalise("---\ntitle: T\nauthor: A\nfoo: bar\n---\nBody\n", "md2pdf")
        self.assertTrue(source.text.startswith("---\ntitle: T\nauthor: A\n---\n"))
        self.assertNotIn("foo", source.text)

    def test_paper_and_font_size(self):
        self.assertEqual(pdfmd.native_paper({"papersize": "Letter"}), "letter")
        self.assertEqual(pdfmd.native_paper({"papersize": "a4paper"}), "a4")
        self.assertEqual(pdfmd.native_paper({}), "a4")
        self.assertEqual(pdfmd.native_font_size({"fontsize": "11pt"}), 11.0)
        self.assertIsNone(pdfmd.native_font_size({"fontsize": "huge"}))


class MathAsTextTests(unittest.TestCase):
    def test_converter(self):
        cases = {
            r"E=mc^2": "*E* = *mc*<sup>2</sup>",
            r"\alpha_i + \beta^{-1} \le \sqrt{x^2+y^2}":
                "α<sub>*i*</sub> + β<sup>−1</sup> ≤ √(*x*<sup>2</sup> + *y*<sup>2</sup>)",
            r"\sum_{i=1}^{n} i = \frac{n(n+1)}{2}": "∑<sub>*i*=1</sub><sup>*n*</sup>*i* = (*n*(*n* + 1))/2",
            r"\frac13": "1/3",
            r"-x + y": "−*x* + *y*",
            r"\mathbb{R}^n": "ℝ<sup>*n*</sup>",
            r"a < b": "*a* &lt; *b*",
        }
        for source, expected in cases.items():
            self.assertEqual(pdfmd.inline_math(source), expected, source)

    def test_unicode_scripts_when_html_is_not_available(self):
        self.assertEqual(pdfmd.inline_math("x^2 + y_i", html=False), "*x*² + *y*ᵢ")
        self.assertEqual(pdfmd.inline_math("x^{a/b}", html=False), "*x*^(a/b)")

    def test_display_blocks_are_stacked_and_centred_for_inkmd(self):
        source, counts = pdfmd.normalise_gfm("Text\n\n$$\n\\begin{aligned} a &= b \\\\ c &= d \\end{aligned}\n$$\n", "inkmd")
        self.assertEqual(counts["math_text"], 1)
        rows = [row for row in source.text.splitlines() if "*a*" in row or "*c*" in row]
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertTrue(row.startswith("\u200b\u00a0\u200b"), repr(row[:6]))
            self.assertGreater(row.count("\u00a0"), 40)
        self.assertTrue(rows[0].endswith("\\"))  # hard line break between the two

    def test_single_line_display_and_inline_in_text(self):
        source, _ = pdfmd.normalise_gfm("Inline $x^2$ and $$y_1$$ in text.\n", "inkmd")
        self.assertIn("Inline *x*<sup>2</sup> and *y*<sub>1</sub> in text.", source.text)

    def test_a_dollar_pair_at_line_start_with_trailing_text_is_inline(self):
        text = "$$a$$ is first, then more.\n\nSecond paragraph.\n\n$$b$$\n\nThird.\n"
        source, counts = pdfmd.normalise_gfm(text, "inkmd")
        self.assertIn("*a* is first, then more.", source.text)
        self.assertIn("Second paragraph.", source.text)
        self.assertIn("Third.", source.text)
        self.assertEqual(counts["math_text"], 2)

    def test_prices_and_code_are_not_math(self):
        source, counts = pdfmd.normalise_gfm("Costs $5 and $6, code `$x$`.\n", "inkmd")
        self.assertIn("Costs $5 and $6, code `$x$`.", source.text)
        self.assertNotIn("math", counts)

    def test_md2pdf_writes_prices_as_entities_but_not_math(self):
        source, _ = pdfmd.normalise_gfm("Costs $5 and $6, math $x$, code `$y$`.\n", "md2pdf")
        self.assertIn("Costs &#36;5 and &#36;6, math $x$, code `$y$`.", source.text)

    def test_md2pdf_is_not_given_a_paragraph_straight_after_its_own_marker(self):
        plain, _ = pdfmd.normalise_gfm("Starts with text.\n", "md2pdf")
        self.assertTrue(plain.text.startswith("&nbsp;\n\n"))
        heading, _ = pdfmd.normalise_gfm("# Heading\n\nText.\n", "md2pdf")
        self.assertTrue(heading.text.startswith("# Heading"))

    @unittest.skipUnless(pdfmd.matplotlib_available(), "matplotlib is not installed")
    def test_md2pdf_keeps_what_mathtext_reads_and_sets_the_rest_as_text(self):
        source, counts = pdfmd.normalise_gfm(
            "Inline $E=mc^2$ and $\\tfrac13$ and $$\\int_0^1 x\\,dx$$ and\n\n$$\n\\begin{aligned} a &= b \\\\ c &= d \\end{aligned}\n$$\n",
            "md2pdf")
        self.assertIn("$E=mc^2$", source.text)
        self.assertIn("$\\frac13$", source.text.replace("\\frac{1}{3}", "\\frac13"))
        self.assertEqual(counts.get("math_text"), 1)
        self.assertIn("*a* = *b*\\\n*c* = *d*", source.text)


class EngineSelectionTests(unittest.TestCase):
    def select(self, requested=None, presentation=False, pandoc=True, engines=(), md2pdf=False):
        def which(name):
            return "/bin/" + name if (name == "pandoc" and pandoc) or name in engines else None

        # engine_executable() resolves soffice beyond PATH (e.g. the macOS app
        # bundle), so it must be mocked too or a real LibreOffice leaks in.
        with mock.patch.object(pdfmd, "which", which), \
                mock.patch.object(pdfmd, "resolve_soffice", lambda: which("soffice")), \
                mock.patch.object(pdfmd, "md2pdf_available", lambda: md2pdf):
            return pdfmd.select_engines(requested, presentation)

    def test_pandoc_route_is_unchanged(self):
        self.assertEqual(self.select(engines=("xelatex", "typst")), ["xelatex", "typst"])
        self.assertEqual(self.select("typst", engines=("typst",)), ["typst"])

    def test_no_pandoc_falls_back_to_native(self):
        self.assertEqual(self.select(pandoc=False, engines=("xelatex",)), ["inkmd"])
        self.assertEqual(self.select(pandoc=False, md2pdf=True), ["md2pdf", "inkmd"])

    def test_pandoc_without_any_engine_falls_back_to_native(self):
        self.assertEqual(self.select(), ["inkmd"])

    def test_explicit_native_requests(self):
        self.assertEqual(self.select("inkmd", pandoc=False), ["inkmd"])
        self.assertEqual(self.select("ink", engines=("xelatex",)), ["inkmd"])
        self.assertEqual(self.select("native", md2pdf=True), ["md2pdf", "inkmd"])
        self.assertEqual(self.select("md2pdf", md2pdf=True), ["md2pdf"])

    def test_missing_md2pdf_is_an_error_not_a_silent_downgrade(self):
        with self.assertRaises(SystemExit) as caught:
            self.select("md2pdf")
        # On Python 3.10 the honest hint is the version requirement instead.
        hint = "Python 3.11" if sys.version_info < (3, 11) else "pdfmd --install math"
        self.assertIn(hint, str(caught.exception))

    def test_a_pandoc_engine_request_needs_pandoc(self):
        with self.assertRaises(SystemExit) as caught:
            self.select("lualatex", pandoc=False, engines=("lualatex",))
        self.assertIn("Pandoc was not found", str(caught.exception))
        with self.assertRaises(SystemExit):
            self.select("tex", pandoc=False, engines=("lualatex",))

    def test_slides_never_use_the_native_tier(self):
        with self.assertRaises(SystemExit):
            self.select(presentation=True)
        with self.assertRaises(SystemExit):
            self.select("inkmd", presentation=True)


class NativeOrderTests(unittest.TestCase):
    def order(self, text, math_available=True):
        source, _ = pdfmd.normalise_gfm(text, "inkmd")
        with mock.patch.object(pdfmd, "matplotlib_available", lambda: math_available):
            return pdfmd.native_order(["md2pdf", "inkmd"], source)

    def test_plain_document_prefers_inkmd(self):
        self.assertEqual(self.order("Just text.\n"), ["inkmd", "md2pdf"])

    def test_footnotes_title_and_math_prefer_md2pdf(self):
        self.assertEqual(self.order("A[^1]\n\n[^1]: n\n")[0], "md2pdf")
        self.assertEqual(self.order("---\ntitle: T\n---\nBody\n")[0], "md2pdf")
        self.assertEqual(self.order("Math $x^2$ here.\n")[0], "md2pdf")

    def test_math_without_matplotlib_prefers_inkmd(self):
        self.assertEqual(self.order("Math $x^2$ here.\n", math_available=False)[0], "inkmd")


class PdfmdWithoutPandocTests(unittest.TestCase):
    """The real command line, with nothing but Python on PATH."""

    def run_pdfmd(self, *arguments, cwd):
        empty = Path(cwd) / "empty-bin"
        empty.mkdir(exist_ok=True)
        environment = {**os.environ, "PATH": str(empty), "PDFMD_NO_PROMPT": "1"}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], cwd=cwd,
                              env=environment, capture_output=True, text=True)

    def test_markdown_to_pdf_with_no_pandoc(self):
        with tempfile.TemporaryDirectory() as directory:
            document = Path(directory) / "doc.md"
            document.write_text((FIXTURES / "pandoc.md").read_text(encoding="utf-8"), encoding="utf-8")
            result = self.run_pdfmd("doc.md", "-e", "inkmd", cwd=directory)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("NATIVE", result.stdout)
            self.assertIn("front-matter keys not used", result.stderr)
            pdf = Path(directory) / "doc.pdf"
            self.assertTrue(pdf.read_bytes().startswith(b"%PDF-"))
            if pypdf is not None:
                info = pypdf.PdfReader(pdf).metadata
                self.assertEqual(info.title, "Pandoc-flavoured")
                self.assertEqual(info.author, "Ada Example, Bob Example")
                self.assertEqual(info.creator, "inkmd via pdfmd-cli")

    def test_automatic_fallback_announces_itself(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "doc.md").write_text("# Hi\n\nText\n", encoding="utf-8")
            result = self.run_pdfmd("doc.md", cwd=directory)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("NOTE  Pandoc was not found: building with the built-in renderer", result.stdout)
            self.assertTrue((Path(directory) / "doc.pdf").is_file())

    def test_things_that_need_pandoc_still_say_so(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "doc.md").write_text("# Hi\n", encoding="utf-8")
            for arguments in (["doc.md", "-o", "doc.html"], ["doc.md", "-p"], ["doc.md", "-e", "xelatex"]):
                result = self.run_pdfmd(*arguments, cwd=directory)
                self.assertNotEqual(result.returncode, 0, arguments)
                self.assertIn("Pandoc was not found", result.stdout + result.stderr, arguments)

    def test_non_markdown_input_is_refused_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "doc.rst").write_text("Title\n=====\n", encoding="utf-8")
            result = self.run_pdfmd("doc.rst", cwd=directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Markdown only", result.stdout + result.stderr)

    def test_check_dependencies_reports_native_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_pdfmd("--check-dependencies", cwd=directory)
            self.assertEqual(result.returncode, 0)
            self.assertIn("Mode: native only", result.stdout)


class InstallToolsTests(unittest.TestCase):
    """`pdfmd --install pandoc|typst|full`, with the network and pip faked."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        patcher = mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(root / "data"),
                                               "LOCALAPPDATA": str(root / "data")})
        patcher.start()
        self.addCleanup(patcher.stop)
        quiet = contextlib.ExitStack()
        quiet.enter_context(contextlib.redirect_stdout(io.StringIO()))
        quiet.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.addCleanup(quiet.close)

    def archive(self, name: str) -> bytes:
        import tarfile
        import zipfile
        buffer = io.BytesIO()
        script = b"#!/bin/sh\necho typst 9.9.9\n"
        if name.endswith(".zip"):
            with zipfile.ZipFile(buffer, "w") as bundle:
                bundle.writestr("typst-x/typst.exe", script)
                bundle.writestr("typst-x/LICENSE", b"x")
        else:
            with tarfile.open(fileobj=buffer, mode="w:xz") as bundle:
                for member, payload in (("typst-x/typst", script), ("typst-x/LICENSE", b"x")):
                    info = tarfile.TarInfo(member)
                    info.size = len(payload)
                    bundle.addfile(info, io.BytesIO(payload))
        return buffer.getvalue()

    def fake_download(self, payload: bytes):
        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return mock.patch.object(pdfmd.urllib.request, "urlopen", lambda *a, **k: Response(payload))

    def install(self, name: str, sha256: str | None):
        payload = self.archive(name)
        digest = hashlib.sha256(payload).hexdigest() if sha256 == "good" else sha256
        version = subprocess.CompletedProcess([], 0, stdout="typst 9.9.9\n", stderr="")
        with mock.patch.object(pdfmd, "typst_asset_name", lambda: name), \
                mock.patch.object(pdfmd, "github_release_asset", lambda repo, asset: ("https://example.invalid/" + asset, digest)), \
                mock.patch.object(pdfmd.subprocess, "run", lambda *a, **k: version), \
                self.fake_download(payload):
            return pdfmd.install_typst()

    def test_asset_names_per_platform(self):
        names = {("Linux", "x86_64"): "typst-x86_64-unknown-linux-musl.tar.xz",
                 ("Linux", "aarch64"): "typst-aarch64-unknown-linux-musl.tar.xz",
                 ("Darwin", "arm64"): "typst-aarch64-apple-darwin.tar.xz",
                 ("Darwin", "x86_64"): "typst-x86_64-apple-darwin.tar.xz",
                 ("Windows", "AMD64"): "typst-x86_64-pc-windows-msvc.zip",
                 ("Windows", "ARM64"): "typst-aarch64-pc-windows-msvc.zip",
                 ("Linux", "riscv64"): None, ("FreeBSD", "x86_64"): None}
        for (system, machine), expected in names.items():
            self.assertEqual(pdfmd.typst_asset_name(system, machine), expected, (system, machine))

    def test_typst_install_from_tar_and_zip(self):
        for name, executable in (("typst-x86_64-unknown-linux-musl.tar.xz", "typst"),
                                 ("typst-x86_64-pc-windows-msvc.zip", "typst.exe")):
            with self.subTest(name):
                self.assertTrue(self.install(name, "good"))
                installed = pdfmd.tools_directory() / executable
                self.assertTrue(installed.is_file())
                self.assertEqual(installed.read_bytes(), b"#!/bin/sh\necho typst 9.9.9\n")
                if sys.platform != "win32":
                    self.assertTrue(os.access(installed, os.X_OK))
                self.assertFalse(list(pdfmd.tools_directory().glob("*.part")))
                installed.unlink()

    def test_a_wrong_checksum_installs_nothing(self):
        self.assertFalse(self.install("typst-x86_64-unknown-linux-musl.tar.xz", "0" * 64))
        self.assertFalse(pdfmd.tools_directory().exists() and list(pdfmd.tools_directory().iterdir()))

    def test_works_without_a_checksum_and_says_so(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertTrue(self.install("typst-x86_64-unknown-linux-musl.tar.xz", None))
        self.assertIn("no checksum was available", output.getvalue())
        self.assertNotIn("SHA-256 verified", output.getvalue())

    def test_a_verified_download_says_so(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertTrue(self.install("typst-x86_64-unknown-linux-musl.tar.xz", "good"))
        self.assertIn("SHA-256 verified", output.getvalue())
        self.assertNotIn("no checksum", output.getvalue())

    def test_the_missing_pandoc_message_offers_the_installer(self):
        self.assertIn("pdfmd --install pandoc", pdfmd.PANDOC_MISSING)
        self.assertIn("Pandoc was not found", pdfmd.PANDOC_MISSING)

    def test_release_lookup_falls_back_to_the_latest_download_link(self):
        def offline(*args, **kwargs):
            raise OSError("no network")

        with mock.patch.object(pdfmd.urllib.request, "urlopen", offline):
            url, digest = pdfmd.github_release_asset("typst/typst", "typst-x.tar.xz")
        self.assertEqual(url, "https://github.com/typst/typst/releases/latest/download/typst-x.tar.xz")
        self.assertIsNone(digest)

    def test_release_lookup_reads_the_digest(self):
        release = json.dumps({"assets": [{"name": "typst-x.tar.xz", "browser_download_url": "https://e/x",
                                          "digest": "sha256:abc123"}]}).encode()

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        with mock.patch.object(pdfmd.urllib.request, "urlopen", lambda *a, **k: Response(release)):
            self.assertEqual(pdfmd.github_release_asset("typst/typst", "typst-x.tar.xz"), ("https://e/x", "abc123"))

    def test_managed_tools_come_after_the_users_own_path(self):
        folder = pdfmd.tools_directory()
        folder.mkdir(parents=True)
        with mock.patch.dict(os.environ, {"PATH": os.pathsep.join(["/first", "/second"])}):
            pdfmd.use_managed_tools()
            pdfmd.use_managed_tools()
            entries = os.environ["PATH"].split(os.pathsep)
        self.assertEqual(entries[:2], ["/first", "/second"])
        self.assertEqual(entries.count(str(folder)), 1)

    def test_bundled_pandoc_is_found_through_pypandoc(self):
        root = Path(self.directory.name) / "site"
        (root / "pypandoc" / "files").mkdir(parents=True)
        (root / "pypandoc" / "__init__.py").write_text("")
        (root / "pypandoc" / "files" / "pandoc").write_text("")
        (root / "pypandoc" / "files" / "pandoc.exe").write_text("")
        sys.path.insert(0, str(root))
        try:
            importlib_invalidate = __import__("importlib").invalidate_caches
            importlib_invalidate()
            sys.modules.pop("pypandoc", None)
            self.assertEqual(pdfmd.bundled_pandoc_directory(), root / "pypandoc" / "files")
        finally:
            sys.path.remove(str(root))
            sys.modules.pop("pypandoc", None)

    def test_pandoc_and_full_installs(self):
        done = subprocess.CompletedProcess([], 0)
        with mock.patch.object(pdfmd.subprocess, "run", lambda *a, **k: done) as run:
            self.assertTrue(pdfmd.install_extra("pandoc"))
        with mock.patch.object(pdfmd.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 1)):
            self.assertFalse(pdfmd.install_extra("pandoc"))
        calls = []
        with mock.patch.object(pdfmd, "install_extra", wraps=pdfmd.install_extra) as wrapped, \
                mock.patch.object(pdfmd, "install_typst", lambda: calls.append("typst") or True), \
                mock.patch.object(pdfmd.subprocess, "run", lambda *a, **k: done):
            self.assertTrue(pdfmd.install_extra("full"))
        self.assertEqual(calls, ["typst"])
        self.assertEqual([call.args[0] for call in wrapped.call_args_list], ["full", "pandoc", "typst"])

    def test_every_install_kind_is_known(self):
        for kind in pdfmd.INSTALL_KINDS:
            self.assertIn(kind, pdfmd.INSTALL_SIZES)
        self.assertEqual(set(pdfmd.INSTALL_SPECS), {"emoji", "math", "pandoc", "translit"})


@unittest.skipUnless(pdfmd.md2pdf_available(), "pymd2pdf is not installed (pdfmd --install math)")
class Md2pdfTests(unittest.TestCase):
    def test_renders_footnotes_and_sets_the_title(self):
        with tempfile.TemporaryDirectory() as directory:
            document = Path(directory) / "doc.md"
            document.write_text("---\ntitle: Via md2pdf\nauthor: Ada\n---\n\nText[^1]\n\n[^1]: Note.\n",
                                encoding="utf-8")
            ok, reason = pdfmd.convert_native(document, Path(directory) / "doc.pdf", ["md2pdf"], [],
                                              None, False, False)
            self.assertTrue(ok, reason)
            data = (Path(directory) / "doc.pdf").read_bytes()
            self.assertTrue(data.startswith(b"%PDF-"))
            if pypdf is not None:
                self.assertEqual(pypdf.PdfReader(Path(directory) / "doc.pdf").metadata.title, "Via md2pdf")


if __name__ == "__main__":
    unittest.main()
