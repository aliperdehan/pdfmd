"""Beamer writer selection through the checkout launcher."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
BEAMER = re.compile(r"\\documentclass\s*(?:\[[^\]]*\])?\s*\{beamer\}")


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Presentation(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="pdfmd-presentation-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                    "PYTHONIOENCODING": "utf-8",
                    "XDG_CONFIG_HOME": str(self.root / "config"), "APPDATA": str(self.root / "config"),
                    "XDG_CACHE_HOME": str(self.root / "cache"), "XDG_DATA_HOME": str(self.root / "data")}

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_pdfmd(self, *args, success=True):
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), *args,
                               "--no-backup", "--no-stamp", "--rewrite"], cwd=self.root, env=self.env,
                              stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8", timeout=90)
        output = done.stdout + done.stderr
        if success:
            self.assertEqual(done.returncode, 0, output)
        else:
            self.assertNotEqual(done.returncode, 0, output)
        return output

    def tex(self, *args, name="deck"):
        self.run_pdfmd(f"{name}.md", "--stop-at", "tex", *args)
        return (self.root / f"{name}.tex").read_text(encoding="utf-8")

    def check_cli_off(self, *args):
        self.assertRegex(self.tex(*args), BEAMER)
        self.assertNotRegex(self.tex(*args, "--no-presentation"), BEAMER)

    def test_document_setting_and_cli_off(self):
        self.write("deck.md", "---\npdfmd-options: {presentation: true}\n---\n\n## Slide\n")
        self.check_cli_off()

    def test_folder_setting_and_cli_off(self):
        self.write("project/.pdfmd/config.yaml", "options: {presentation: true}\n")
        self.write("project/deck.md", "## Slide\n")
        self.assertRegex(self.tex(name="project/deck"), BEAMER)
        self.assertNotRegex(self.tex("--no-presentation", name="project/deck"), BEAMER)

    def test_kit_mode_metadata_and_defaults_and_cli_off(self):
        self.write("slides.kit/.kit", """kit-format: 1
name: slides
modes:
  inline:
    metadata: {pdfmd-options: {presentation: true}}
  from-file:
    defaults: slides.yaml
""")
        self.write("slides.kit/slides.yaml", "pdfmd-options: {presentation: true}\n")
        for mode in ("inline", "from-file"):
            with self.subTest(mode=mode):
                self.write("deck.md", f"---\npdfmd-options: {{kit: {{'./slides.kit': {mode}}}}}\n---\n\n## Slide\n")
                self.check_cli_off()

    def test_global_and_discovered_metadata_follow_existing_precedence(self):
        self.env["PDFMD_CONFIG"] = str(self.write("config/global.yaml", "options: {presentation: true}\n"))
        self.write("deck.md", "## Slide\n")
        self.assertRegex(self.tex(), BEAMER)
        self.write("deck.yaml", "pdfmd-options: {presentation: false}\n")
        self.assertNotRegex(self.tex(), BEAMER)
        self.write("deck.md", "---\npdfmd-options: {presentation: true}\n---\n\n## Slide\n")
        self.assertRegex(self.tex(), BEAMER)

    def test_cli_on_overrides_false(self):
        self.write("deck.md", "---\npdfmd-options: {presentation: false}\n---\n\n## Slide\n")
        self.assertNotRegex(self.tex(), BEAMER)
        self.assertRegex(self.tex("-p"), BEAMER)

    def test_incompatible_routes_name_the_source(self):
        deck = self.write("deck.md", "---\npdfmd-options: {presentation: true}\n---\n\n## Slide\n")
        self.write("plain.md", "## Ordinary text\n")
        self.write("deck.qmd", deck.read_text(encoding="utf-8"))
        self.write(".pdfmd/config.yaml", "options: {presentation: true}\n")
        (self.root / "deck.docx").write_bytes(b"PK\x80")
        for args, reason, source in (
            (("deck.md", "--stop-at", "markdown"), "--stop-at markdown", "deck.md's front matter"),
            (("deck.md", "--to", "html"), "--to/-o", "deck.md's front matter"),
            (("-b", "deck.md", "plain.md", "--to", "doc"), "--to/-o", "deck.md's front matter"),
            (("deck.md", "--section", "Slide"), "--section", "deck.md's front matter"),
            (("--book", "deck.md", "plain.md", "--stop-at", "tex"), "--report/--book", "deck.md's front matter"),
            (("--report", "deck.md", "plain.md", "--to", "doc"), "--report/--book", "deck.md's front matter"),
            (("deck.md", "-e", "inkmd"), "Pandoc's Beamer writer", "deck.md's front matter"),
            (("deck.qmd", "--stop-at", "tex"), ".qmd", "deck.qmd's front matter"),
            (("deck.docx", "--stop-at", "tex"), "office-document input", str(Path(".pdfmd") / "config.yaml")),
        ):
            with self.subTest(args=args):
                output = self.run_pdfmd(*args, success=False)
                self.assertIn(reason, output)
                self.assertIn("presentation: true in ", output)
                self.assertIn(source, output)

    def test_batch_resolves_presentation_for_each_document(self):
        self.write("deck.md", "---\npdfmd-options: {presentation: true}\n---\n\n## Slide\n")
        self.write("plain.md", "## Ordinary text\n")
        for jobs in ("1", "2"):
            with self.subTest(jobs=jobs):
                self.run_pdfmd("-b", "deck.md", "plain.md", "--stop-at", "tex", "-j", jobs, "-o", f"build-{jobs}")
                self.assertRegex((self.root / f"build-{jobs}" / "deck.tex").read_text(encoding="utf-8"), BEAMER)
                self.assertNotRegex((self.root / f"build-{jobs}" / "plain.tex").read_text(encoding="utf-8"), BEAMER)

    def test_raw_latex_environments_keep_their_groups_in_beamer(self):
        raw = (
            r"\begin{center}{\itshape grouped}\end{center}",
            "\n".join((r"\begin{samepage}", r"{\itshape together}", r"\end{samepage}")),
            "\n".join((r"\begin{landscape}", r"{\itshape wide}", r"\end{landscape}")),
            r"\begin{center}",
            r"{\itshape split}",
            r"\end{center}",
        )
        source = "\n\n".join(f"```{{=latex}}\n{block}\n```" for block in raw)
        self.write("deck.md", f"---\ntitle: Raw environments\n---\n\n## Slide\n\n{source}\n")
        for args in ((), ("-p",)):
            with self.subTest(args=args):
                tex = self.tex(*args)
                for block in raw:
                    self.assertIn(block, tex)
                self.assertEqual(tex.count(r"\begin{center}"), 2)
                self.assertEqual(tex.count(r"\end{center}"), 2)

    def test_beamer_uses_its_own_margins(self):
        self.write("deck.md", "---\ntitle: Wide deck\nclassoption: [aspectratio=169]\n---\n\n## Slide\n")
        self.assertIn("margin=1in", self.tex())
        for args in (("deck.md", "-p", "--stop-at", "tex"),
                     ("deck.md", "--to", "beamer"),
                     ("-r", "deck.md", "--to", "beamer", "-o", "deck.tex", "-V", "documentclass=beamer")):
            with self.subTest(args=args):
                log = self.run_pdfmd(*args, "--verbose")
                tex = (self.root / "deck.tex").read_text(encoding="utf-8")
                self.assertRegex(tex, BEAMER)
                self.assertIn("aspectratio=169", tex)
                self.assertNotIn("margin=1in", tex)
                self.assertNotIn("no geometry/margin set", log)

    def test_beamer_keeps_explicit_margins(self):
        self.write("deck.md", "---\nmargin: 7mm\n---\n\n## Slide\n")
        self.assertIn(r"\geometry{margin=7mm}", self.tex("-p"))
        config = self.write("config/settings.yaml", "options: {}\n")
        self.env["PDFMD_CONFIG"] = str(config)
        self.write("config/metadata.yaml", "geometry: margin=8mm\n")
        self.write("deck.md", "## Slide\n")
        self.assertIn(r"\geometry{margin=8mm}", self.tex("-p"))
        self.assertIn(r"\geometry{margin=9mm}", self.tex("-p", "-V", "geometry:margin=9mm"))

    def test_kit_can_still_suppress_the_article_default_margin(self):
        self.write("slides.kit/.kit", "kit-format: 1\nname: slides\nno-auto: [margin]\n")
        self.write("deck.md", "---\npdfmd-options: {kit: './slides.kit'}\n---\n\n## Slide\n")
        self.assertNotIn("margin=1in", self.tex())
        self.assertIn(r"\geometry{margin=9mm}", self.tex("-p", "-V", "geometry:margin=9mm"))
