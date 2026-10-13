"""v3.28.34: the picture cache's protocol between pdfmd and a LaTeX package is neutral (nothing in pdfmd names a package):
a package opts in by mentioning `pdfmdCacheDir`; a request's context may carry a plain-catcode part and ask for two runs;
v3.28.37: the names a package used before the protocol had neutral ones (LabPlotCacheDir, .plotreq, Lab@pc@wd ...) are
its own business, in `<package>-pdfmd.yaml` (`picture-cache:`): aliases, defined and read as well."""

from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

# A stand-in for lualatex: it makes the job's PDF and the .dim file the job opens, and notes each run.
FAKE_ENGINE = """#!/bin/sh
for last; do :; done
for argument; do case "$argument" in -output-directory=*) out="${argument#-output-directory=}";; esac; done
stem=$(basename "$last" .tex)
echo "$stem" >> "$out/runs.log"
cp "$last" "$out/job-$(wc -l < "$out/runs.log" | tr -d ' ').tex"
dim=$(sed -n 's/.*openout.dimf=\\([^ ]*\\)$/\\1/p' "$last" | head -1)
printf '%%PDF-1.4\\n' > "$out/$stem.pdf"
printf '\\\\gdef\\\\x{1}' > "$out/$dim"
"""


class Names(unittest.TestCase):
    def test_the_handshake_is_neutral_and_no_package_is_named(self):
        self.assertEqual(pdfmd.CACHE_HANDSHAKE, "pdfmdCacheDir")
        source = (ROOT / "pdfmd.py").read_text(encoding="utf-8")
        for word in ("LabPlot", "Lab@pc"):
            self.assertNotIn(word, source, word)                   # the first package's names are its helper's, not pdfmd's


@unittest.skipUnless(shutil.which("kpsewhich"), "needs kpsewhich")
class Styles(unittest.TestCase):
    def test_a_package_that_mentions_the_handshake_takes_part_and_others_do_not(self):
        with tempfile.TemporaryDirectory() as folder:
            tree = Path(folder) / "texmf" / "tex" / "latex"
            (tree / "cachey").mkdir(parents=True)
            (tree / "plain").mkdir()
            (tree / "cachey" / "cachey.sty").write_text("\\ProvidesPackage{cachey}\n\\ifdefined\\pdfmdCacheDir\\fi\n",
                                                        encoding="utf-8")
            (tree / "plain" / "plain.sty").write_text("\\ProvidesPackage{plain}\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"TEXMFHOME": str(Path(folder) / "texmf")}):
                preamble = ("\\documentclass{article}\n\\usepackage[draft]{cachey,plain}\n"
                            "% \\usepackage{notloaded}\n\\RequirePackage{missing-package}\n")
                found = pdfmd.picture_cache_styles(preamble)
        self.assertEqual([name for name, _, _ in found], ["cachey"])
        self.assertIn("pdfmdCacheDir", found[0][1])
        self.assertEqual(found[0][2], {})

    def test_a_package_helper_gives_the_aliases_and_counts_as_the_handshake(self):
        with tempfile.TemporaryDirectory() as folder:
            tree = Path(folder) / "texmf" / "tex" / "latex" / "oldy"
            tree.mkdir(parents=True)
            (tree / "oldy.sty").write_text("\\ProvidesPackage{oldy}\n\\ifdefined\\OldyDir\\fi\n", encoding="utf-8")
            (tree / "oldy-pdfmd.yaml").write_text(
                "picture-cache:\n  dir: OldyDir\n  render: OldyRender\n  requests: .oldyreq\n"
                "  wd: Oldy@wd\n  ht: Oldy@ht\n  dp: Oldy@dp\n  bogus: x\n  dir2: \"a b\"\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"TEXMFHOME": str(Path(folder) / "texmf")}):
                found = pdfmd.picture_cache_styles("\\usepackage{oldy}")
        self.assertEqual([name for name, _, _ in found], ["oldy"])
        self.assertEqual(found[0][2]["dir"], "OldyDir")
        self.assertNotIn("bogus", found[0][2])
        merged = pdfmd.cache_aliases(found)
        self.assertEqual((merged["requests"], merged["wd"]), ([".oldyreq"], ["Oldy@wd"]))


@unittest.skipIf(sys.platform == "win32", "a shell script stands in for the engine")
class Render(unittest.TestCase):
    ALIASES = {"render": ["OldyRender"], "wd": ["Oldy@wd"], "ht": ["Oldy@ht"], "dp": ["Oldy@dp"]}

    def render(self, ctx: str, aliases=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        engine = root / "fakelatex"
        engine.write_text(FAKE_ENGINE.replace("%%", "%"), encoding="utf-8")
        engine.chmod(engine.stat().st_mode | stat.S_IEXEC)
        plots = root / "plots"
        plots.mkdir()
        key = "0" * 32
        done, failed = pdfmd.render_plot_requests({key: ("\\Thing", "{body}", ctx)}, plots, "\\documentclass{article}\n",
                                                  str(engine), root, None, [root], False, aliases)
        return plots, key, done, failed

    def test_a_plain_request_runs_once_with_the_neutral_and_the_alias_names_defined(self):
        plots, key, done, failed = self.render("\\textwidth=10pt", self.ALIASES)
        self.assertEqual((done, failed), (1, 0))
        self.assertEqual((plots / "runs.log").read_text().split(), [f"r-{key}"])
        job = (plots / "job-1.tex").read_text(encoding="utf-8")
        self.assertTrue(job.startswith("\\def\\pdfmdCacheRender{}\\def\\OldyRender{}\n"))
        for name in ("pdfmdCacheWd", "Oldy@wd", "pdfmdCacheHt", "Oldy@ht", "pdfmdCacheDp", "Oldy@dp"):
            self.assertIn("\\string\\" + name, job)
        self.assertIn("\\ExplSyntaxOn\n\\textwidth=10pt\n\\ExplSyntaxOff\n\n\\setbox", job)
        self.assertTrue((plots / f"{key}.pdf").exists() and (plots / f"{key}.dim").exists())

    def test_a_margin_makes_the_page_the_box_plus_that_on_every_side(self):
        # ink that overflows the box (a label raised above it) must not be cut off
        plots, key, done, failed = self.render("\\textwidth=10pt" + pdfmd.PLOT_CTX_PLAIN + "@@margin=56pt@@")
        self.assertEqual((done, failed), (1, 0))
        job = (plots / "job-1.tex").read_text(encoding="utf-8")
        self.assertNotIn("@@", job)
        self.assertIn("\\string\\gdef\\string\\pdfmdCacheMargin{56pt}", job)
        self.assertIn("\\pagewidth=\\dimexpr\\wd\\z@+2\\dimexpr56pt\\relax", job)
        self.assertIn("\\shipout\\vbox{\\kern56pt\\hbox{\\kern56pt\\box\\z@\\kern56pt}\\kern56pt}", job)
        self.assertIn("\\ifdefined\\pdfmdCachePost", job)                 # a unit's side effects are stored for a hit
        plain, _, _ = self.render("\\textwidth=10pt")[:3]
        self.assertIn("\\shipout\\hbox{\\box\\z@}", (plain / "job-1.tex").read_text(encoding="utf-8"))   # no margin: the page as before

    def test_the_plain_part_is_read_outside_expl3_and_two_runs_can_be_asked_for(self):
        ctx = "\\textwidth=10pt" + pdfmd.PLOT_CTX_PLAIN + pdfmd.PLOT_CTX_TWICE + "\\setKV[x]{atom sep={1em}}"
        plots, key, done, failed = self.render(ctx)
        self.assertEqual((done, failed), (1, 0))
        self.assertEqual(len((plots / "runs.log").read_text().split()), 2)
        job = (plots / "job-1.tex").read_text(encoding="utf-8")
        self.assertIn("\\ExplSyntaxOn\n\\textwidth=10pt\n\\ExplSyntaxOff\n\\setKV[x]{atom sep={1em}}\n\\setbox", job)
        self.assertNotIn("@@", job)


if __name__ == "__main__":
    unittest.main()
