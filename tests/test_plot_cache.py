"""The plot cache's folders and inputs (v3.27.28): each document keeps its own plots, a part built alone uses the full
build's, a `tlmgr update` starts afresh, and a file of the user's own TeX tree is an input like a CSV. The whole
cache (a build, a hit, a CSV edit) is checked end to end by nulabreport's smoke test (plot_cache_check.py)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os as _os, tempfile as _tempfile  # noqa: E402
_os.environ["PDFMD_CONFIG"] = ""
_os.environ["XDG_CONFIG_HOME"] = _tempfile.mkdtemp(prefix="pdfmd-test-config-")

import pdfmd  # noqa: E402


class CacheCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        patcher = mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.root / "cache"),
                                               "LOCALAPPDATA": str(self.root / "cache")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def document(self, folder: str) -> Path:
        path = self.root / folder / "report.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Report\n\ntext\n", encoding="utf-8")
        return path


PREAMBLE = "\\documentclass{article}\n\\usepackage{nulabreport}\n\\title{LR4-5}\n"
# what a part built alone adds: the label replay names a temporary file, so it differs at every build
REPLAY = ("\\AtBeginDocument{\\InputIfFileExists{\"/tmp/pdfmd-labels-%s/labels-aux-seed.tex\"}{}{}}\n"
          "\\makeatletter\n\\providecommand\\pdfmd@seed[2]{}\n\\makeatother\n")


class Folders(CacheCase):
    def test_a_part_built_alone_finds_the_full_builds_plots(self):
        full = pdfmd.plot_cache_directory(pdfmd.plot_preamble(PREAMBLE, []), "sty", "lualatex", self.root)
        for run in ("abc123", "def456"):
            replay = REPLAY % run
            part = pdfmd.plot_preamble(PREAMBLE + replay + "\\hypersetup{hidelinks}\n", [replay])
            self.assertEqual(part, PREAMBLE + "\\hypersetup{hidelinks}\n")
            self.assertNotEqual(pdfmd.plot_cache_directory(part, "sty", "lualatex", self.root), full)   # a real change
            self.assertEqual(pdfmd.plot_cache_directory(pdfmd.plot_preamble(PREAMBLE + replay, [replay]), "sty",
                                                        "lualatex", self.root), full)

    def test_nor_does_its_title(self):
        # LR4-5's Discussion: nulabreport's filter drops a part's title page, and Pandoc wraps the PDF title differently
        full = ("\\hypersetup{\n  pdftitle={Reduction of -Cinnamaldehyde with Sodium Borohydride},\n  pdflang={en-GB}}\n"
                "\\title{Reduction of \\emph{trans}-Cinnamaldehyde\nwith Sodium Borohydride}\n\\author{A}\n")
        part = ("\\hypersetup{\n  pdftitle={Reduction of -Cinnamaldehyde with\nSodium Borohydride},\n  pdflang={en-GB}}\n"
                "\\author{A}\n")
        self.assertEqual(pdfmd.plot_cache_directory(PREAMBLE + full, "sty", "lualatex", self.root),
                         pdfmd.plot_cache_directory(PREAMBLE + part, "sty", "lualatex", self.root))
        self.assertEqual(pdfmd.plot_key_text(full), "\\hypersetup{ pdflang={en-GB}} \\author{A}")
        self.assertNotEqual(pdfmd.plot_cache_directory(PREAMBLE + full, "sty", "lualatex", self.root),
                            pdfmd.plot_cache_directory(PREAMBLE + part.replace("en-GB", "de-DE"), "sty", "lualatex",
                                                       self.root))

    def test_each_document_keeps_its_own(self):
        # one shared folder kept the three newest: building three other reports threw a report's plots away
        mine = pdfmd.cache_directory(self.document("lr4"))
        kept = pdfmd.plot_cache_directory(PREAMBLE, "sty", "lualatex", mine)
        kept.mkdir(parents=True)
        self.assertEqual(kept.parent, mine)
        for number in range(5):
            other = pdfmd.cache_directory(self.document(f"other{number}"))
            folder = pdfmd.plot_cache_directory(PREAMBLE + f"% {number}\n", "sty", "lualatex", other)
            folder.mkdir(parents=True)
            pdfmd.prune_plot_directories(folder)
        self.assertTrue(kept.is_dir())

    def test_a_tex_live_update_starts_a_new_folder(self):
        tlpdb = self.root / "texlive" / "tlpkg" / "texlive.tlpdb"
        tlpdb.parent.mkdir(parents=True)
        tlpdb.write_text("name 00texlive.config\n", encoding="utf-8")
        answer = subprocess.CompletedProcess([], 0, stdout=str(self.root / "texlive") + "\n", stderr="")
        folders = []
        for when in (1_700_000_000, 1_800_000_000):            # `tlmgr update` rewrites the database
            os.utime(tlpdb, (when, when))
            pdfmd.tex_tree_stamp.cache_clear()
            with mock.patch.object(pdfmd, "which", lambda name: "/usr/bin/kpsewhich"), \
                    mock.patch.object(pdfmd.subprocess, "run", return_value=answer):
                self.assertTrue(pdfmd.tex_tree_stamp())
                folders.append(pdfmd.plot_cache_directory(PREAMBLE, "sty", "lualatex", self.root))
        pdfmd.tex_tree_stamp.cache_clear()
        self.assertNotEqual(*folders)

    def test_no_tex_live_no_stamp(self):
        pdfmd.tex_tree_stamp.cache_clear()
        self.addCleanup(pdfmd.tex_tree_stamp.cache_clear)
        with mock.patch.object(pdfmd, "which", lambda name: None):
            self.assertEqual(pdfmd.tex_tree_stamp(), "")


class Inputs(CacheCase):
    def setUp(self):
        super().setUp()
        self.report = self.root / "lab"
        (self.report / "ir").mkdir(parents=True)
        self.csv = self.report / "ir" / "product.csv"
        self.csv.write_text("4000,90\n", encoding="utf-8")
        self.tree = self.root / "texmf"
        (self.tree / "tex" / "latex" / "pkg").mkdir(parents=True)
        self.vendored = self.tree / "tex" / "latex" / "pkg" / "chemfig.tex"
        self.vendored.write_text("% chemfig\n", encoding="utf-8")
        self.texlive = self.root / "texlive" / "pgfplots.sty"
        self.texlive.parent.mkdir(parents=True)
        self.texlive.write_text("% pgfplots\n", encoding="utf-8")

    def recorded(self, plots: Path) -> dict:
        job = plots / "r-k1.tex"
        job.write_text("\\documentclass{article}\n", encoding="utf-8")
        fls = plots / "r-k1.fls"
        fls.write_text(f"PWD {self.report}\nINPUT {job}\nINPUT ./ir/product.csv\nINPUT {self.vendored}\n"
                       f"INPUT {self.texlive}\nINPUT {plots / 'r-k1.aux'}\n", encoding="utf-8")
        return pdfmd.plot_recorded_inputs(fls, [self.report, self.tree])

    def test_the_users_own_tex_tree_counts_tex_lives_does_not(self):
        plots = self.root / "cache" / "plots-abc"
        plots.mkdir(parents=True)
        self.assertEqual(set(self.recorded(plots)), {str(self.csv), str(self.vendored)})

    @unittest.skipUnless(os.name == "nt", "a drive letter, and its case, exist only on Windows")
    def test_a_lower_case_drive_letter_is_still_the_reports_folder(self):
        # TeX writes `d:/work/lab/ir/product.csv` where the report's folder is `D:\work\lab`; the CSV was dropped as
        # foreign and an edit to it showed as a stale plot
        plots = self.root / "cache" / "plots-abc"
        plots.mkdir(parents=True)
        spelled = str(self.csv).replace("\\", "/")
        spelled = spelled[0].swapcase() + spelled[1:]
        self.assertNotEqual(spelled[0], str(self.csv)[0])
        fls = plots / "r-k1.fls"
        fls.write_text(f"PWD {self.report}\nINPUT {spelled}\n", encoding="utf-8")
        found = pdfmd.plot_recorded_inputs(fls, [self.report, self.tree])
        self.assertEqual([os.path.normcase(name) for name in found], [os.path.normcase(str(self.csv))])

    def test_a_cache_beside_the_document_does_not_record_its_own_job(self):
        # `location: document`: the plot folder is under the report's folder, and the job's .tex (deleted once it
        # has run) was recorded as an input, so every entry was dropped at the next build
        plots = self.report / ".cache" / "pdfmd" / "report" / "plots-abc"
        plots.mkdir(parents=True)
        deps = self.recorded(plots)
        self.assertEqual(set(deps), {str(self.csv), str(self.vendored)})
        (plots / "r-k1.tex").unlink()
        (plots / "k1.deps").write_text(json.dumps({**deps, "__roots__": [str(self.report), str(self.tree)]}),
                                       encoding="utf-8")
        for suffix in (".pdf", ".dim"):
            (plots / f"k1{suffix}").write_text("x", encoding="utf-8")
        self.assertEqual(pdfmd.validate_plot_entries(plots, False, [self.report, self.tree]), 0)
        self.vendored.write_text("% chemfig, updated with the package\n", encoding="utf-8")
        self.assertEqual(pdfmd.validate_plot_entries(plots, False, [self.report, self.tree]), 1)
        self.assertFalse((plots / "k1.pdf").exists())

    def test_the_users_trees_come_from_kpsewhich(self):
        answers = {"TEXMFHOME": f"{self.tree}\n", "TEXMFLOCAL": f"{{{self.root / 'missing'},{self.tree}}}\n"}

        def run(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, stdout=answers[command[-1]], stderr="")

        pdfmd.user_tex_trees.cache_clear()
        self.addCleanup(pdfmd.user_tex_trees.cache_clear)
        with mock.patch.object(pdfmd, "which", lambda name: "/usr/bin/kpsewhich"), \
                mock.patch.object(pdfmd.subprocess, "run", run):
            self.assertEqual(pdfmd.user_tex_trees(), (Path(os.path.abspath(self.tree)),))


if __name__ == "__main__":
    unittest.main()
