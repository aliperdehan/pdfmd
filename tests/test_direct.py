"""The direct routes: a `.typ` file to Typst and an `.html` file to an HTML engine or a browser, no Pandoc."""

from __future__ import annotations

import base64
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402
import pdfmd_direct as direct  # noqa: E402

PAGE = ('<!doctype html><html><head><meta charset="utf-8"><title>P</title><style>@page{size:A5;margin:15mm}</style>'
        "</head><body><h1>Hello page</h1></body></html>")
SCRIPTED = PAGE.replace("</body>", "<script>document.title='x'</script></body>")
MATHML = PAGE.replace("</body>", '<p><math display="inline"><msup><mi>x</mi><mn>2</mn></msup></math></p></body>')
TYPST = "#set page(width: 12cm, height: 6cm, margin: 1cm)\n= Typst doc\nA *bold* word.\n"


def fake(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


class Choosing(unittest.TestCase):
    def setUp(self):
        self.bin = Path(tempfile.mkdtemp(prefix="pdfmd-direct-bin-"))
        self.addCleanup(shutil.rmtree, self.bin, True)
        for name in ("weasyprint", "wkhtmltopdf", "chromium", "microsoft-edge"):
            fake(self.bin, name, "exit 0")
        self.which = lambda name: str(self.bin / name) if (self.bin / name).exists() else None
        # find_browser also looks in the folders browsers install to; the machine's own Chrome must not leak in
        patcher = mock.patch.object(direct.html, "sys", types.SimpleNamespace(platform="linux"))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.dict(os.environ, {"PDFMD_BROWSER": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def names(self, text, request=None):
        return [name for name, _ in direct.html_attempts(text, request, self.which)]

    def test_a_plain_page_goes_to_weasyprint_first_and_a_scripted_one_to_a_browser(self):
        self.assertEqual(self.names(PAGE), ["weasyprint", "chromium", "edge", "wkhtmltopdf"])
        self.assertEqual(self.names(SCRIPTED), ["chromium", "edge", "weasyprint", "wkhtmltopdf"])

    def test_a_page_with_mathml_goes_to_a_browser_first(self):
        # WeasyPrint prints MathML as flat text (v3.27.12)
        self.assertTrue(direct.has_mathml(MATHML))
        self.assertFalse(direct.has_mathml(PAGE.replace("Hello", "the math class")))
        self.assertEqual(self.names(MATHML), ["chromium", "edge", "weasyprint", "wkhtmltopdf"])

    def test_data_scripts_are_not_code(self):
        self.assertFalse(direct.has_scripts('<script type="application/ld+json">{}</script>'))
        self.assertTrue(direct.has_scripts("<SCRIPT src=a.js></SCRIPT>"))

    def test_a_request_narrows_the_list(self):
        self.assertEqual(self.names(PAGE, "wkhtmltopdf"), ["wkhtmltopdf"])
        self.assertEqual(self.names(PAGE, "browser"), ["chromium", "edge"])
        self.assertEqual(self.names(PAGE, "edge"), ["edge"])
        self.assertEqual(self.names(PAGE, "prince"), [])                   # not installed: nothing to try

    def test_an_engine_of_another_kind_is_not_a_request_for_this_route(self):
        self.assertFalse(direct.html_accepts_request("lualatex"))
        self.assertTrue(direct.html_accepts_request("weasy"))
        self.assertTrue(direct.html_accepts_request(None))
        self.assertFalse(direct.typst_accepts_request("xelatex"))
        self.assertTrue(direct.typst_accepts_request("typst"))


@unittest.skipIf(os.name == "nt", "the stand-in programs are sh scripts")
class Rendering(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-direct-render-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        (self.directory / "page.html").write_text(PAGE, encoding="utf-8")
        self.bin = self.directory / "bin"
        self.bin.mkdir()

    def test_the_next_engine_is_tried_when_one_fails(self):
        fake(self.bin, "weasyprint", "echo 'boom: cannot draw this' >&2; exit 1")
        fake(self.bin, "wkhtmltopdf", 'for last; do :; done; printf %%PDF-fake > "$last"')
        order = [("weasyprint", str(self.bin / "weasyprint")), ("wkhtmltopdf", str(self.bin / "wkhtmltopdf"))]
        failures = []
        ok, reason, used = direct.render_html(self.directory / "page.html", self.directory / "out.pdf", order,
                                              on_failure=lambda name, why, rest: failures.append((name, why, rest)))
        self.assertTrue(ok, reason)
        self.assertEqual(used, "wkhtmltopdf")
        self.assertEqual(failures, [("weasyprint", "boom: cannot draw this", ["wkhtmltopdf"])])
        self.assertTrue((self.directory / "out.pdf").is_file())

    def test_a_browser_that_stays_running_after_writing_the_pdf_is_stopped(self):
        fake(self.bin, "chromium", 'for a; do case "$a" in --print-to-pdf=*) printf %%PDF-fake > "${a#--print-to-pdf=}";; esac; done; sleep 60')
        import time
        started = time.monotonic()
        ok, reason, used = direct.render_html(self.directory / "page.html", self.directory / "out.pdf",
                                              [("chromium", str(self.bin / "chromium"))])
        self.assertTrue(ok, reason)
        self.assertEqual(used, "chromium")
        self.assertLess(time.monotonic() - started, 20)

    def test_every_engine_failing_gives_the_last_reason(self):
        fake(self.bin, "weasyprint", "echo nope >&2; exit 2")
        ok, reason, used = direct.render_html(self.directory / "page.html", self.directory / "out.pdf",
                                              [("weasyprint", str(self.bin / "weasyprint"))])
        self.assertFalse(ok)
        self.assertEqual((reason, used), ("nope", None))
        self.assertFalse((self.directory / "out.pdf").exists())


class Route(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-direct-route-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.page = self.directory / "page.html"
        self.page.write_text(PAGE, encoding="utf-8")

    def test_the_decision(self):
        typst = self.directory / "d.typ"
        typst.write_text(TYPST, encoding="utf-8")
        have_typst = bool(pdfmd.engine_executable("typst"))
        if have_typst:
            self.assertEqual(pdfmd.direct_route(typst, "pdf", None, None, None, False), "typst")
            self.assertIsNone(pdfmd.direct_route(typst, "pdf", None, ["typstdirect"], None, False))
            self.assertIsNone(pdfmd.direct_route(typst, "pdf", "markdown", None, None, False))
            self.assertIsNone(pdfmd.direct_route(typst, "pdf", None, None, "lualatex", False))
        self.assertIsNone(pdfmd.direct_route(typst, "docx", None, None, None, False))
        self.assertIsNone(pdfmd.direct_route(self.directory / "x.md", "pdf", None, None, None, False))
        if shutil.which("weasyprint"):
            self.assertEqual(pdfmd.direct_route(self.page, "pdf", None, None, None, False), "html")
            self.assertEqual(pdfmd.direct_route(self.page, "pdf", "html", None, None, False), "html")
            self.assertIsNone(pdfmd.direct_route(self.page, "pdf", None, ["htmldirect"], None, False))


@unittest.skipUnless(shutil.which("typst"), "needs Typst")
class TypstEndToEnd(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-direct-typst-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        (self.directory / "d.typ").write_text(TYPST, encoding="utf-8")
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.directory / "xdg"), "APPDATA": str(self.directory / "xdg"), "PDFMD_CONFIG": ""}

    def run_pdfmd(self, *args, env=None):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=self.directory,
                              capture_output=True, text=True, env=env or self.env)

    def test_the_documents_own_page_size_survives(self):
        done = self.run_pdfmd("d.typ", "--verbose")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("TYPSTDIRECT", done.stdout)
        if shutil.which("pdfinfo"):
            info = subprocess.run(["pdfinfo", str(self.directory / "d.pdf")], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
            self.assertIn("340.157 x 170.079", info)                      # 12 cm x 6 cm

    def test_no_pandoc_is_needed(self):
        bin_dir = self.directory / "bin"
        bin_dir.mkdir()
        typst = Path(shutil.which("typst"))
        try:
            (bin_dir / typst.name).symlink_to(typst)                      # typst.exe by its own name on Windows, where a link needs a privilege
        except OSError:
            shutil.copy2(typst, bin_dir / typst.name)
        done = self.run_pdfmd("d.typ", env={**self.env, "PATH": str(bin_dir)})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.directory / "d.pdf").is_file())

    def test_a_typst_error_is_reported_and_no_pdf_is_left(self):
        (self.directory / "bad.typ").write_text("#let x = (\n", encoding="utf-8")
        done = self.run_pdfmd("bad.typ")
        self.assertEqual(done.returncode, 1)
        self.assertIn("error", done.stdout + done.stderr)
        self.assertFalse((self.directory / "bad.pdf").exists())

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_no_auto_typstdirect_goes_through_pandoc(self):
        done = self.run_pdfmd("d.typ", "--no-auto", "typstdirect", "--verbose")
        self.assertNotIn("TYPSTDIRECT", done.stdout)


@unittest.skipUnless(shutil.which("weasyprint"), "needs WeasyPrint")
class HtmlEndToEnd(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-direct-html-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        (self.directory / "page.html").write_text(PAGE, encoding="utf-8")
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.directory / "xdg"), "APPDATA": str(self.directory / "xdg"), "PDFMD_CONFIG": ""}

    def test_the_pages_own_size_survives(self):
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "page.html", "--verbose"], cwd=self.directory,
                              capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("HTMLDIRECT", done.stdout)
        if shutil.which("pdfinfo"):
            info = subprocess.run(["pdfinfo", str(self.directory / "page.pdf")], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
            self.assertIn("419.528 x 595.276", info)                      # A5


class Defaults(unittest.TestCase):
    META = {"title": 'My "Report"', "author": ["Ada", "Bob"], "date": "2026-10-09", "lang": "en-US",
            "mainfont": "STIX Two Text", "fontsize": "12", "geometry": "margin=2cm", "papersize": "letter"}

    def test_the_settings_are_read_from_the_first_file_that_has_them(self):
        found = direct.defaults.collect([{"title": "First", "geometry": "margin=2cm"}, {"title": "Second", "author": "Ada",
                                                                                         "fontsize": "11pt"}])
        self.assertEqual((found["title"], found["margin"], found["author"], found["fontsize"]),
                         ("First", "2cm", ["Ada"], "11pt"))
        self.assertEqual(direct.defaults.collect([{"fontsize": "huge", "papersize": "a99", "margin": "wide"}]), {})

    def test_typst_gets_set_rules_and_keeps_what_the_document_says(self):
        found = direct.defaults.collect([self.META])
        prelude = direct.defaults.typst_prelude(found, "= Heading")
        self.assertIn('#set document(title: "My \\"Report\\"", author: ("Ada", "Bob",), date: datetime(year: 2026, month: 10, day: 9))', prelude)
        self.assertIn('#set text(lang: "en", font: "STIX Two Text", size: 12pt)', prelude)
        self.assertIn('#set page(paper: "us-letter", margin: 2cm)', prelude)
        own = direct.defaults.typst_prelude(found, '#set document(title: "Mine")\n= H')
        self.assertNotIn("title:", own)

    def test_html_gets_a_head_block_before_the_pages_own_styles(self):
        found = direct.defaults.collect([self.META])
        page = '<html><head><style>body{color:red}</style></head><body>x</body></html>'
        done = direct.defaults.apply_to_html(found, page)
        self.assertIn("<title>My &quot;Report&quot;</title>", done)
        self.assertLess(done.index("font-family"), done.index("color:red"))
        self.assertIn('<html lang="en-US">', done)
        self.assertIn('@page { size: letter; margin: 2cm }', done)
        titled = direct.defaults.apply_to_html(found, "<html lang='fr'><head><title>Own</title></head></html>")
        self.assertEqual(titled.count("<title"), 1)
        self.assertIn("lang='fr'", titled)
        bare = direct.defaults.apply_to_html(found, "<p>just a fragment</p>")
        self.assertTrue(bare.startswith("<head>"))


@unittest.skipUnless(shutil.which("typst"), "needs Typst")
class ApplyDefaultsEndToEnd(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-direct-defaults-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        (self.directory / "d.typ").write_text("= Doc\nText.\n", encoding="utf-8")
        (self.directory / "metadata.yaml").write_text("title: From Metadata\nauthor: Ada\npapersize: a6\n", encoding="utf-8")
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.directory / "xdg"), "APPDATA": str(self.directory / "xdg"), "PDFMD_CONFIG": ""}

    def run_pdfmd(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=self.directory,
                              capture_output=True, text=True, env=self.env)

    @unittest.skipUnless(shutil.which("pdfinfo"), "needs pdfinfo")
    def test_defaults_are_applied_only_when_asked(self):
        self.assertEqual(self.run_pdfmd("d.typ", "-o", "plain.pdf").returncode, 0)
        plain = subprocess.run(["pdfinfo", str(self.directory / "plain.pdf")], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        self.assertNotIn("From Metadata", plain)
        done = self.run_pdfmd("d.typ", "--apply-defaults", "-o", "with.pdf")
        self.assertEqual(done.returncode, 0, done.stderr)
        info = subprocess.run(["pdfinfo", str(self.directory / "with.pdf")], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        self.assertIn("From Metadata", info)
        self.assertIn("297.638 x 419.528", info)                             # A6
        self.assertEqual([item.name for item in self.directory.iterdir() if "pdfmd-defaults" in item.name], [])

    def test_the_config_can_make_it_the_default_and_the_flag_can_turn_it_off(self):
        config = self.directory / "config.yaml"
        config.write_text("options:\n  apply-defaults: true\n", encoding="utf-8")
        self.env["PDFMD_CONFIG"] = str(config)
        done = self.run_pdfmd("d.typ", "--verbose", "-o", "a.pdf")
        self.assertIn("APPLYDEFAULTS", done.stdout)
        done = self.run_pdfmd("d.typ", "--verbose", "--no-apply-defaults", "-o", "b.pdf")
        self.assertNotIn("APPLYDEFAULTS", done.stdout)

    def test_a_typst_error_names_the_file_and_its_own_line(self):
        (self.directory / "bad.typ").write_text("= Fine\n#let x = (\n", encoding="utf-8")
        done = self.run_pdfmd("bad.typ", "--apply-defaults")
        self.assertEqual(done.returncode, 1)
        self.assertIn("bad.typ:2:", done.stdout + done.stderr)
        self.assertNotIn("pdfmd-defaults", done.stdout + done.stderr)


@unittest.skipUnless(shutil.which("pandoc") and (shutil.which("lualatex") or shutil.which("xelatex") or shutil.which("pdflatex")),
                     "needs Pandoc and a LaTeX engine")
class TexFallback(unittest.TestCase):
    def test_a_tex_file_no_engine_can_compile_is_tried_through_pandoc(self):
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-direct-tex-"))
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / "broken.tex").write_text("\\documentclass{article}\n\\usepackage{nosuchpackagexyz}\n"
                                              "\\begin{document}\nHello fallback.\n\\end{document}\n", encoding="utf-8")
        env = {**os.environ, "XDG_CONFIG_HOME": str(directory / "xdg"), "APPDATA": str(directory / "xdg"), "PDFMD_CONFIG": ""}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "broken.tex"], cwd=directory,
                              capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("direct compilation failed", done.stderr)
        self.assertIn("trying it through Pandoc", done.stderr)
        self.assertTrue((directory / "broken.pdf").is_file())
        again = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "broken.tex", "--no-auto", "texdirect"], cwd=directory,
                               capture_output=True, text=True, env=env)
        self.assertNotIn("direct compilation failed", again.stderr)

    def test_fragment_is_compiled_with_its_project_preamble(self):
        with tempfile.TemporaryDirectory(prefix="pdfmd-tex-fragment-") as folder:
            root = Path(folder)
            (root / "preamble.tex").write_text(
                r"\newcommand{\fixturemacro}[1]{\input{#1}}" + "\n", encoding="utf-8")
            (root / "body.txt").write_text("From the fragment.\n", encoding="utf-8")
            (root / "fragment.tex").write_text(r"\fixturemacro{body.txt}" + "\n", encoding="utf-8")
            engine = next(name for name in ("pdflatex", "xelatex", "lualatex") if shutil.which(name))
            command = [sys.executable, str(ROOT / "scripts/pdfmd"), "fragment.tex", "--verbose", "--no-backup",
                       "-e", engine]
            env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
            done = subprocess.run(command, cwd=root, env=env, capture_output=True, encoding="utf-8")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("TEXFRAGMENT", done.stdout)
            self.assertNotIn("trying it through Pandoc", done.stderr)
            self.assertTrue((root / "fragment.pdf").is_file())
            done = subprocess.run([*command, "--no-auto", "preamble", "-o", "missing.pdf"], cwd=root, env=env,
                                  capture_output=True, encoding="utf-8")
            self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("LaTeX fragment needs its project preamble", done.stdout + done.stderr)
            self.assertFalse((root / "missing.pdf").exists())


TEST_TEX = next((name for name in ("lualatex", "xelatex", "pdflatex") if shutil.which(name)), None)


class IncludedTexResolution(unittest.TestCase):
    def test_fragment_paths_and_missing_reference(self):
        from pdfmd_tex.references import pandoc_sources, tex_source

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            fragment = root / "fragments"
            fragment.mkdir()
            main = root / "main.tex"
            main.write_text(r"\input{fragments/fragment}", encoding="utf-8")
            markdown = root / "main.md"
            raw = r"\input{fragments/fragment}"
            markdown.write_text(f"`{raw}`\n\n```{{=latex}}\n{raw}\n```\n", encoding="utf-8")
            original = ("% \\includegraphics{picture.png}\n"
                        "\\includegraphics[width=1cm]{picture.png}\n"
                        "\\input{nested}\n\\verbatiminput{data.txt}\n\\input{missing}\n")
            body = fragment / "fragment.tex"
            body.write_text(original, encoding="utf-8")
            for path in (root / "picture.png", fragment / "picture.png", fragment / "nested.tex", root / "data.txt"):
                path.write_text("fixture\n", encoding="utf-8")
            warned = set()
            log = StringIO()
            with redirect_stderr(log), tex_source(main, root, root, warned) as prepared:
                head = prepared.read_text(encoding="utf-8")
                shadow = Path(head.split("{")[1].split("}")[0])
                rendered = shadow.read_text(encoding="utf-8")
                self.assertIn("% \\includegraphics{picture.png}", rendered)
                self.assertIn(f"{{{(fragment / 'picture.png').as_posix()}}}", rendered)
                self.assertIn(f"{{{(fragment / 'nested.tex').as_posix()}}}", rendered)
                self.assertIn(f"{{{(root / 'data.txt').as_posix()}}}", rendered)
                self.assertIn(r"\input{missing}", rendered)
            self.assertFalse(shadow.exists())
            self.assertEqual(body.read_text(encoding="utf-8"), original)
            command = ["pandoc", str(markdown), "-o", str(root / "out.pdf")]
            with redirect_stderr(log), pandoc_sources(command, root, root, warned) as prepared:
                source = Path(prepared[1]).read_text(encoding="utf-8")
                self.assertEqual(source.count(raw), 1)
                self.assertIn(f"`{raw}`", source)
            self.assertEqual(log.getvalue().count("WARN  TeX input path:"), 1)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_the_office_filter_uses_the_fragment_before_the_document(self):
        import zipfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = root / "fragments"
            files.mkdir()
            (root / "d.md").write_text(
                "---\ntitle: Example\npdfmd-options: {office: {latex: auto, labels: off}}\n---\n\n"
                "```{=latex}\n\\input{fragments/body}\n```\n", encoding="utf-8")
            (files / "body.tex").write_text("\\input{extra}\n", encoding="utf-8")
            (files / "extra.tex").write_text("Fragment content.\n", encoding="utf-8")
            (root / "extra.tex").write_text("Document content.\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "d.md", "--to", "docx",
                                   "--no-backup", "-o", "result.docx"], cwd=root, capture_output=True,
                                  encoding="utf-8", timeout=120)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            with zipfile.ZipFile(root / "result.docx") as package:
                xml = package.read("word/document.xml")
            self.assertIn(b"Fragment content.", xml)
            self.assertNotIn(b"Document content.", xml)
            self.assertEqual(done.stderr.count("WARN  TeX input path:"), 1, done.stderr)


@unittest.skipUnless(TEST_TEX and shutil.which("pdftotext"), "needs a LaTeX engine and pdftotext")
class IncludedTexPaths(unittest.TestCase):
    def build_cases(self, suffix):
        pixel = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGNgAAAAAgABSK+kcQAAAABJRU5ErkJggg==")
        for where in ("fragment", "document", "both", "missing"):
            with self.subTest(where=where), tempfile.TemporaryDirectory(prefix="pdfmd-input-") as folder:
                root = Path(folder)
                fragment = root / "fragments"
                fragment.mkdir()
                (fragment / "body.tex").write_text(
                    "\\includegraphics[width=1cm]{figure.png}\n\\input{extra}\n\\verbatiminput{data.txt}\n", encoding="utf-8")
                (fragment / "data.txt").write_text("Local data\n", encoding="utf-8")
                for place, word in ((root, "Root copy"), (fragment, "Fragment copy")):
                    if where in ("both", "document" if place == root else "fragment"):
                        (place / "figure.png").write_bytes(pixel)
                        (place / "extra.tex").write_text(word + "\n", encoding="utf-8")
                include = r"\input{fragments/body}"
                packages = "\\usepackage{graphicx}\n\\usepackage{verbatim}\n"
                if suffix == "tex":
                    recipe = "\\documentclass{article}\n" + packages + "\\begin{document}\n" + include + "\n\\end{document}\n"
                else:
                    recipe = "---\ntitle: Example\npdfmd-options: {cache: off}\n---\n\n```{=latex}\n" + include + "\n```\n"
                    (root / "preamble.tex").write_text(packages, encoding="utf-8")
                (root / f"d.{suffix}").write_text(recipe, encoding="utf-8")
                done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), f"d.{suffix}",
                                       "-e", TEST_TEX, "--engine-fallback", "off", "--no-stamp", "--no-backup"],
                                      cwd=root, capture_output=True, encoding="utf-8", timeout=120)
                if where == "missing":
                    self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
                    self.assertIn("figure.png", done.stdout + done.stderr)
                    continue
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                read = subprocess.run(["pdftotext", "d.pdf", "-"], cwd=root, capture_output=True, encoding="utf-8", check=True)
                self.assertIn("Root copy" if where == "document" else "Fragment copy", read.stdout)
                self.assertIn("Local data", read.stdout)
                warnings = [line.replace("\\", "/") for line in done.stderr.splitlines() if "TeX input path" in line]
                self.assertEqual(len(warnings), 2 if where == "both" else 0, done.stderr)
                if where == "both":
                    for name in ("extra.tex", "figure.png"):
                        line = next(warning for warning in warnings if name in warning)
                        document_path = pdfmd.under_home((root / name).resolve()).replace("\\", "/")
                        chosen_path = pdfmd.under_home((fragment / name).resolve()).replace("\\", "/")
                        self.assertIn(document_path, line)
                        self.assertIn(chosen_path, line)
                        self.assertIn(f"using {chosen_path}", line)

    def test_direct_tex(self):
        self.build_cases("tex")

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_markdown_to_pdf(self):
        self.build_cases("md")


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class MarkdownReaderOverride(unittest.TestCase):
    def test_md_means_markdown_even_with_a_tex_suffix(self):
        with tempfile.TemporaryDirectory(prefix="pdfmd-reader-md-") as folder:
            root = Path(folder)
            (root / "read.tex").write_text("# Heading\n\nA **strong** word.\n", encoding="utf-8")
            for args in ((), ("--no-auto", "reader")):
                with self.subTest(args=args):
                    done = subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), "read.tex",
                                           "--from", "md", "--to", "html", "-o", "read.html", *args],
                                          cwd=root, capture_output=True, encoding="utf-8",
                                          env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"})
                    self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                    self.assertIn("<strong>strong</strong>", (root / "read.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
