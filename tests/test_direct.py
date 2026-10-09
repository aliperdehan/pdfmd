"""The direct routes: a `.typ` file to Typst and an `.html` file to an HTML engine or a browser, no Pandoc."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402
import pdfmd_direct as direct  # noqa: E402

PAGE = ('<!doctype html><html><head><meta charset="utf-8"><title>P</title><style>@page{size:A5;margin:15mm}</style>'
        "</head><body><h1>Hello page</h1></body></html>")
SCRIPTED = PAGE.replace("</body>", "<script>document.title='x'</script></body>")
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
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.directory / "xdg"), "PDFMD_CONFIG": ""}

    def run_pdfmd(self, *args, env=None):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=self.directory,
                              capture_output=True, text=True, env=env or self.env)

    def test_the_documents_own_page_size_survives(self):
        done = self.run_pdfmd("d.typ", "--verbose")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("TYPSTDIRECT", done.stdout)
        if shutil.which("pdfinfo"):
            info = subprocess.run(["pdfinfo", str(self.directory / "d.pdf")], capture_output=True, text=True).stdout
            self.assertIn("340.157 x 170.079", info)                      # 12 cm x 6 cm

    def test_no_pandoc_is_needed(self):
        bin_dir = self.directory / "bin"
        bin_dir.mkdir()
        (bin_dir / "typst").symlink_to(shutil.which("typst"))
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
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.directory / "xdg"), "PDFMD_CONFIG": ""}

    def test_the_pages_own_size_survives(self):
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "page.html", "--verbose"], cwd=self.directory,
                              capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("HTMLDIRECT", done.stdout)
        if shutil.which("pdfinfo"):
            info = subprocess.run(["pdfinfo", str(self.directory / "page.pdf")], capture_output=True, text=True).stdout
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
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.directory / "xdg"), "PDFMD_CONFIG": ""}

    def run_pdfmd(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=self.directory,
                              capture_output=True, text=True, env=self.env)

    @unittest.skipUnless(shutil.which("pdfinfo"), "needs pdfinfo")
    def test_defaults_are_applied_only_when_asked(self):
        self.assertEqual(self.run_pdfmd("d.typ", "-o", "plain.pdf").returncode, 0)
        plain = subprocess.run(["pdfinfo", str(self.directory / "plain.pdf")], capture_output=True, text=True).stdout
        self.assertNotIn("From Metadata", plain)
        done = self.run_pdfmd("d.typ", "--apply-defaults", "-o", "with.pdf")
        self.assertEqual(done.returncode, 0, done.stderr)
        info = subprocess.run(["pdfinfo", str(self.directory / "with.pdf")], capture_output=True, text=True).stdout
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
        env = {**os.environ, "XDG_CONFIG_HOME": str(directory / "xdg"), "PDFMD_CONFIG": ""}
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "broken.tex"], cwd=directory,
                              capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("direct compilation failed", done.stderr)
        self.assertIn("trying it through Pandoc", done.stderr)
        self.assertTrue((directory / "broken.pdf").is_file())
        again = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "broken.tex", "--no-auto", "texdirect"], cwd=directory,
                               capture_output=True, text=True, env=env)
        self.assertNotIn("direct compilation failed", again.stderr)


if __name__ == "__main__":
    unittest.main()
