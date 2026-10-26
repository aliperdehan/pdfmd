"""v3.30.42: the paper of a document reaches every engine. `--paper a4,landscape` (also `papersize:` in the front matter, or
`geometry: landscape`) printed a Letter page on the LaTeX engines, stopped Typst, and was not read by WeasyPrint; `--paper letter`
stopped Typst too (two `-V papersize=` that Pandoc joined into `letterus-letter`)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402
from pdfmd_office import units  # noqa: E402

PANDOC = shutil.which("pandoc")


class Words(unittest.TestCase):
    def test_size_and_orientation(self):
        self.assertEqual(pdfmd.paper_words("a4,landscape"), ("a4", "landscape"))
        self.assertEqual(pdfmd.paper_words("Landscape A4"), ("a4", "landscape"))
        self.assertEqual(pdfmd.paper_words("letter"), ("letter", ""))
        self.assertEqual(pdfmd.paper_words("landscape"), ("", "landscape"))
        self.assertEqual(pdfmd.paper_words(None), ("", ""))

    def test_the_other_spellings_of_a_size(self):
        self.assertEqual(pdfmd.paper_words("a4paper"), ("a4", ""))
        self.assertEqual(pdfmd.paper_words("us-letter,portrait"), ("letter", "portrait"))

    def test_the_word_processor_reader_splits_a_list_item_too(self):
        # spec_from_metadata hands it [papersize, *classoption]; 'a4,landscape' was one unknown word there
        self.assertEqual(units.parse_paper(["a4,landscape"]), (units.PAPER_TWIPS["a4"], True))
        self.assertEqual(units.parse_paper(["letter", "landscape"]), (units.PAPER_TWIPS["letter"], True))


class Settled(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def settle(self, kind, variables=(), front="", typo=None):
        path = Path(self.folder.name) / "d.md"
        path.write_text(f"---\ntitle: T\n{front}---\n\nText.\n", encoding="utf-8")
        return pdfmd.paper_variables(path, [], list(variables), typo, kind)

    def test_latex_gets_the_size_as_a_class_option_and_the_orientation_from_geometry(self):
        variables, _ = self.settle("tex", ["papersize=a4,landscape"])
        self.assertEqual(variables, ["papersize=a4", "geometry:landscape"])
        variables, _ = self.settle("tex", front="papersize: letter,landscape\n")
        self.assertEqual(variables, ["papersize=letter", "geometry:landscape"])

    def test_latex_spellings_that_were_no_class_option(self):
        self.assertEqual(self.settle("tex", ["papersize=a4paper"])[0], ["papersize=a4"])
        self.assertEqual(self.settle("tex", ["papersize=us-letter"])[0], ["papersize=letter"])
        self.assertEqual(self.settle("tex", ["papersize=A4"])[0], ["papersize=a4"])
        self.assertEqual(self.settle("tex", ["papersize=a3"])[0], ["geometry:a3paper"])        # the class has no a3

    def test_latex_orientation_alone_leaves_the_size_to_the_settings(self):
        self.assertEqual(self.settle("tex", ["papersize=landscape"])[0], ["geometry:landscape"])
        self.assertEqual(self.settle("tex", front="papersize: landscape\n")[0], ["papersize=", "geometry:landscape"])

    def test_what_is_right_is_not_touched(self):
        variables = ["mainfont=X", "papersize=a4"]
        self.assertEqual(self.settle("tex", variables)[0], variables)
        self.assertEqual(self.settle("tex", front="papersize: a5\n")[0], [])
        self.assertEqual(self.settle("tex")[0], [])
        self.assertEqual(self.settle(None, ["papersize=a4,landscape"])[0], ["papersize=a4,landscape"])
        self.assertEqual(self.settle("calibre", ["papersize=a4,landscape"])[0], ["papersize=a4,landscape"])

    def test_the_pagesize_typo_is_folded_in(self):
        variables, typo = self.settle("tex", typo="a4,landscape")
        self.assertEqual((variables, typo), (["papersize=a4", "geometry:landscape"], None))

    def test_typst_gets_its_own_name_and_one_papersize(self):
        self.assertEqual(self.settle("typst", ["papersize=letter"])[0], ["papersize=us-letter"])     # was two, joined by Pandoc
        self.assertEqual(self.settle("typst", ["papersize=a4,landscape"])[0], ["papersize=a4", "pdfmd-page-flipped=true"])
        self.assertEqual(self.settle("typst", ["papersize=b5"])[0], ["papersize=iso-b5"])
        self.assertEqual(self.settle("typst", front="geometry: landscape\n")[0], ["pdfmd-page-flipped=true"])
        self.assertEqual(self.settle("typst", front="classoption: landscape\npapersize: legal\n")[0],
                         ["papersize=us-legal", "pdfmd-page-flipped=true"])
        self.assertEqual(self.settle("typst")[0], [])

    def test_weasyprint_gets_the_page_in_points_only_when_one_is_asked_for(self):
        self.assertEqual(self.settle("weasyprint", ["papersize=letter"])[0], ["pdfmd-page=612pt 792pt"])
        self.assertEqual(self.settle("weasyprint", front="papersize: letter,landscape\n")[0], ["pdfmd-page=792pt 612pt"])
        self.assertEqual(self.settle("weasyprint", front="geometry: landscape\n")[0], ["pdfmd-page=landscape"])
        self.assertEqual(self.settle("weasyprint")[0], [])

    def test_a_paper_given_by_variable_wins_over_the_front_matter(self):
        self.assertEqual(self.settle("typst", ["papersize=a5"], front="papersize: letter\n")[0], ["papersize=a5"])

    def test_bare_orientation_keeps_the_size_the_settings_gave(self):
        path = Path(self.folder.name) / "d.md"
        path.write_text("---\npapersize: a5\n---\n\nText.\n", encoding="utf-8")
        merged = pdfmd.effective_metadata(path, [], ["papersize=landscape"])
        self.assertEqual(pdfmd.paper_words(merged["papersize"]), ("a5", "landscape"))

    def test_the_pagesize_typo_beats_a_papersize_of_the_settings_for_the_word_processor_readers(self):
        path = Path(self.folder.name) / "d.md"
        path.write_text("---\npagesize: letter\n---\n\nText.\n", encoding="utf-8")
        self.assertEqual(pdfmd.effective_metadata(path, [], [])["papersize"], "letter")


@unittest.skipUnless(PANDOC, "Pandoc is needed")
class Command(unittest.TestCase):
    """Through pdfmd itself: the command Pandoc is given."""

    def test_latex_source_carries_the_paper_and_the_landscape(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "d.md"
            source.write_text("---\ntitle: T\n---\n\nText.\n", encoding="utf-8")
            output = Path(folder) / "d.tex"
            subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), str(source), "--to", "latex", "--paper", "a4,landscape",
                            "-o", str(output)], capture_output=True, text=True, cwd=folder)
            text = output.read_text(encoding="utf-8")
        self.assertIn("a4paper,", text)
        self.assertNotIn("landscapepaper", text)
        self.assertRegex(text, r"\\usepackage\[[^\]]*landscape[^\]]*\]\{geometry\}")


if __name__ == "__main__":
    unittest.main()
