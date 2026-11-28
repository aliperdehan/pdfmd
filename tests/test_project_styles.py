"""Project templates, citation styles and style sheets through the checkout."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[1]
PANDOC = shutil.which("pandoc")


@unittest.skipUnless(PANDOC, "needs Pandoc")
class ProjectStyles(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.root / "config"
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.config), "APPDATA": str(self.config)}
        self.write("sample.md", "Sample body.\n")

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def build(self, writer, *args, output_name="result.out"):
        output = self.root / output_name
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "sample.md",
                               "--to", writer, "-o", str(output), "--no-stamp", "--no-backup", "--verbose", *args],
                              cwd=self.root, env=self.env, capture_output=True, encoding="utf-8", timeout=120)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return output.read_text(encoding="utf-8"), done.stdout + done.stderr

    def test_writer_and_location_order(self):
        self.write("config/pdfmd/template.html5", "<main>Config $body$</main>\n")
        self.write("templates/sample.html5", "<main>Nested $body$</main>\n")
        self.write("template.html5", "<main>Root $body$</main>\n")
        self.write("sample.html", "<main>Document $body$</main>\n")
        self.write("template.latex", "% Latex template\n$body$\n")
        for name, marker in (("sample.html", "Document"), ("template.html5", "Root"),
                             ("templates/sample.html5", "Nested"), ("config/pdfmd/template.html5", "Config")):
            with self.subTest(name=name):
                output, log = self.build("html")
                self.assertIn(f"<main>{marker} ", output)
                self.assertRegex(log, rf"AUTO TEMPLATE\s+[^\n]*{Path(name).name}")
            (self.root / name).unlink()
        output, _ = self.build("latex")
        self.assertIn("% Latex template", output)

    def test_a_previous_html_export_is_skipped_during_discovery(self):
        self.build("html", "--build-log", "on", output_name="sample.html")
        self.write("template.html5", "<main>Template $body$</main>\n")
        output, _ = self.build("html")
        self.assertIn("<main>Template ", output)

    def test_other_text_writers_choose_their_own_template(self):
        for writer in ("beamer", "context", "typst", "revealjs"):
            self.write(f"templates/template.{writer}", f"Fixture {writer}\n$body$\n")
        for writer in ("beamer", "context", "typst", "revealjs"):
            with self.subTest(writer=writer):
                output, log = self.build(writer)
                self.assertIn(f"Fixture {writer}", output)
                self.assertIn(f"template.{writer}", log)

    def test_explicit_template_and_opt_out(self):
        self.write("template.html5", "<main>Automatic $body$</main>\n")
        self.write("chosen.html", "<main>Explicit $body$</main>\n")
        self.write("sample.md", "---\npdfmd-options: {template: chosen.html}\n---\n\nBody.\n")
        output, log = self.build("html", "--no-auto", "template")
        self.assertIn("<main>Explicit ", output)
        self.assertIn("AUTO TEMPLATE", log)
        self.write("cli.html", "<main>CLI $body$</main>\n")
        output, _ = self.build("html", "--template=cli.html")
        self.assertIn("<main>CLI ", output)
        self.write("sample.md", "Body.\n")
        output, log = self.build("html", "--no-auto", "template")
        self.assertNotIn("<main>Automatic ", output)
        self.assertNotIn("AUTO TEMPLATE", log)

    def test_defaults_template_precedes_discovery(self):
        self.write("template.html5", "<main>Automatic $body$</main>\n")
        self.write("chosen.html", "<main>Defaults $body$</main>\n")
        self.write("defaults.yaml", "template: chosen.html\n")
        output, _ = self.build("html", "--defaults=defaults.yaml")
        self.assertIn("<main>Defaults ", output)

    def test_html_template_in_a_report(self):
        self.write("sample.md", "---\nchapter: 1\npdfmd-options: {report-build: patch}\n---\n\nFirst.\n")
        self.write("chapter.md", "---\nchapter: 2\n---\n\nSecond.\n")
        self.write("template.html5", "<main>Report $body$</main>\n")
        output, _ = self.build("html", "--report", "chapter.md")
        self.assertIn("<main>Report ", output)
        self.assertIn("First.", output)
        self.assertIn("Second.", output)

    def test_explicit_css_and_local_discovery(self):
        self.write("templates/sample.css", "body { color: red }\n")
        self.write("pdfmd.css", "body { color: blue }\n")
        self.write("sample.css", "body { color: green }\n")
        output, log = self.build("html", "--standalone")
        self.assertIn("sample.css", output)
        self.assertNotIn("pdfmd.css", output)
        self.assertRegex(log, r"AUTO CSS\s+[^\n]*sample\.css")
        self.write("sample.md", "---\npdfmd-options: {no-auto: [css]}\n---\n\nSample body.\n")
        output, _ = self.build("html", "--standalone")
        self.assertNotIn("sample.css", output)
        self.write("sample.md", "Sample body.\n")
        self.write("chosen.css", "body { color: black }\n")
        output, _ = self.build("html", "--standalone", "--css", "chosen.css")
        self.assertIn("chosen.css", output)
        self.assertNotIn("sample.css", output)
        self.write("defaults.yaml", "css: [chosen.css]\n")
        output, _ = self.build("html", "--standalone", "--defaults=defaults.yaml")
        self.assertIn("chosen.css", output)
        self.assertNotIn("sample.css", output)

    @unittest.skipUnless(shutil.which("typst"), "needs Typst")
    def test_pdf_carries_the_template_used_by_its_writer(self):
        import pdfmd

        if pdfmd.pypdf is None:
            self.skipTest("needs pypdf")
        self.write("templates/sample.typst", "Fixture.\n\n$body$\n")
        self.write("template.latex", "% Wrong writer\n$body$\n")
        output = self.root / "result.pdf"
        command = [sys.executable, str(ROOT / "scripts" / "pdfmd"), "sample.md", "-e", "typst",
                   "-o", str(output), "--attach-source", "--verbose"]
        for flags, expected in (([], False), (["--attach-template"], True),
                                (["--bundle", "all", "--no-attach-template"], False)):
            with self.subTest(flags=flags):
                done = subprocess.run([*command, *flags], cwd=self.root, env=self.env, capture_output=True,
                                      encoding="utf-8", timeout=120)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                reader = pdfmd.pypdf.PdfReader(output)
                manifest = json.loads(reader.attachments[pdfmd.ATTACH_MANIFEST][0])
                files = {entry["path"] for entry in manifest.get("extras", [])}
                self.assertEqual("templates/sample.typst" in files, expected)
                self.assertRegex(done.stdout, r"AUTO TEMPLATE\s+[^\n]*sample\.typst")

    def test_csl_from_templates_and_explicit_style(self):
        self.write("sample.md", "---\nreferences:\n- {id: book, type: book, title: A Book}\n---\n\nSee [@book].\n")
        style = ('<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text">'
                 '<info><title>Fixture</title><id>http://example.invalid/style</id></info>'
                 '<citation><layout prefix="MARKER "><text variable="title"/></layout></citation>'
                 '<bibliography><layout><text variable="title"/></layout></bibliography></style>')
        self.write("templates/sample.csl", style)
        self.write("csl.csl", style.replace("MARKER", "ROOT STYLE"))
        output, log = self.build("html")
        self.assertIn("ROOT STYLE A Book", " ".join(output.split()))
        self.assertRegex(log, r"AUTO CSL\s+[^\n]*csl\.csl")
        (self.root / "csl.csl").unlink()
        output, log = self.build("html")
        self.assertIn("MARKER A Book", " ".join(output.split()))
        self.assertRegex(log, r"AUTO CSL\s+[^\n]*sample\.csl")
        output, _ = self.build("html", "--no-auto", "csl")
        self.assertNotIn("MARKER", output)
        self.write("explicit.csl", style.replace("MARKER", "EXPLICIT STYLE"))
        output, _ = self.build("html", "--csl=explicit.csl")
        self.assertIn("EXPLICIT STYLE A Book", " ".join(output.split()))
        self.write("defaults.yaml", "csl: explicit.csl\n")
        output, _ = self.build("html", "--defaults=defaults.yaml")
        self.assertIn("EXPLICIT STYLE A Book", " ".join(output.split()))


class TemplateAttachment(unittest.TestCase):
    def test_an_external_template_is_restored_under_templates(self):
        import pdfmd

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = root / "project" / "sample.md"
            document.parent.mkdir()
            document.write_text("Body.\n", encoding="utf-8")
            template = root / "common.latex"
            template.write_text("Template $body$\n", encoding="utf-8")
            with mock.patch.object(pdfmd, "TEMPLATE_ATTACH_CLI", True):
                _, _, manifest = pdfmd.source_attachments(
                    document, root / "sample.pdf", [], [], [], None, template=template.resolve())
            self.assertIn("templates/common.latex", {entry["path"] for entry in manifest["extras"]})

    def test_only_opted_in_template_is_attached_in_plain_and_bundled_source(self):
        import pdfmd

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = root / "sample.md"
            document.write_text("Body.\n", encoding="utf-8")
            template = root / "templates" / "sample.latex"
            template.parent.mkdir()
            template.write_text("Template $body$\n", encoding="utf-8")
            for setting in ({}, {"attach-template": True}, {"bundle": "all"}, {"bundle": "all", "attach-template": True}):
                with self.subTest(setting=setting):
                    document.write_text(f"---\npdfmd-options: {json.dumps(setting)}\n---\n\nBody.\n",
                                        encoding="utf-8")
                    with mock.patch.object(pdfmd, "TEMPLATE_ATTACH_CLI", None):
                        _, _, manifest = pdfmd.source_attachments(
                            document, root / "sample.pdf", [], [], [], None, template=template)
                    files = {entry["path"] for entry in manifest.get("extras", [])}
                    self.assertEqual("templates/sample.latex" in files, setting.get("attach-template", False))
