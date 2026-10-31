"""`pdfmd --crop` / pdfmd_crop: a PDF cut to what it draws. The pages are drawn by Ghostscript from PostScript, so the
ink is known exactly."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd_crop  # noqa: E402

GS = shutil.which("gs")
PYPDF = True
try:
    import pypdf  # noqa: E402
except ImportError:
    PYPDF = False


def draw(path: Path, program: str) -> None:
    """A 200 x 100 pt PDF whose pages are drawn by the PostScript `program` (one `showpage` per page)."""
    source = path.with_suffix(".ps")
    source.write_text("<< /PageSize [200 100] >> setpagedevice\n" + program, encoding="ascii")
    subprocess.run([GS, "-q", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pdfwrite", f"-sOutputFile={path}", str(source)], check=True)


def media(path: Path, number: int = 0) -> list[float]:
    page = pypdf.PdfReader(str(path)).pages[number]
    return [round(float(value), 1) for value in page.mediabox]


@unittest.skipUnless(GS and PYPDF, "needs Ghostscript and pypdf")
class Crop(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="pdfmd-test-crop-")
        self.addCleanup(self.scratch.cleanup)
        self.dir = Path(self.scratch.name)
        # page 1: a block at 50..110 x 30..50 and a "page number" at 90..110 x 5..10; page 2: only the block
        self.source = self.dir / "page.pdf"
        draw(self.source, "50 30 60 20 rectfill 90 5 20 5 rectfill showpage 50 30 60 20 rectfill showpage")

    def test_every_page_is_cut_to_its_ink_plus_the_pad(self):
        target = self.dir / "out.pdf"
        done = pdfmd_crop.crop_pdf(self.source, target, pad=2)
        self.assertEqual(done.pages, 2)
        self.assertEqual(media(target, 0), [48.0, 3.0, 112.0, 52.0])   # the page number is ink
        self.assertEqual(media(target, 1), [48.0, 28.0, 112.0, 52.0])
        page = pypdf.PdfReader(str(target)).pages[0]
        self.assertEqual([round(float(v), 1) for v in page.cropbox], media(target, 0))

    def test_the_pad_is_a_setting_and_stops_at_the_page(self):
        target = self.dir / "out.pdf"
        pdfmd_crop.crop_pdf(self.source, target, pad=0, page=2)
        self.assertEqual(media(target), [50.0, 30.0, 110.0, 50.0])
        pdfmd_crop.crop_pdf(self.source, target, pad=500, page=2)
        self.assertEqual(media(target), [0.0, 0.0, 200.0, 100.0])

    def test_the_foot_can_be_left_out(self):
        target = self.dir / "out.pdf"
        pdfmd_crop.crop_pdf(self.source, target, pad=0, ignore_bottom=15, page=1)
        self.assertEqual(media(target), [50.0, 30.0, 110.0, 50.0])

    def test_one_page_alone(self):
        target = self.dir / "out.pdf"
        done = pdfmd_crop.crop_pdf(self.source, target, page=2)
        self.assertEqual(len(pypdf.PdfReader(str(target)).pages), 1)
        self.assertEqual(len(done.boxes), 1)
        with self.assertRaises(pdfmd_crop.CropError):
            pdfmd_crop.crop_pdf(self.source, target, page=3)

    def test_a_rotated_page_is_cut_in_its_own_coordinates(self):
        reader = pypdf.PdfReader(str(self.source))
        writer = pypdf.PdfWriter()
        for angle in (90, 180, 270):
            page = reader.pages[1]
            page.rotate(angle)
            writer.add_page(page)
            page = pypdf.PdfReader(str(self.source)).pages[1]
        rotated = self.dir / "rotated.pdf"
        with open(rotated, "wb") as handle:
            writer.write(handle)
        target = self.dir / "out.pdf"
        pdfmd_crop.crop_pdf(rotated, target, pad=0)
        for number in range(3):
            self.assertEqual(media(target, number), [50.0, 30.0, 110.0, 50.0], f"page {number + 1}")

    def test_a_page_that_draws_nothing_is_left_alone(self):
        blank = self.dir / "blank.pdf"
        draw(blank, "showpage")
        target = self.dir / "out.pdf"
        done = pdfmd_crop.crop_pdf(blank, target)
        self.assertEqual(done.boxes, [None])
        self.assertEqual(media(target), [0.0, 0.0, 200.0, 100.0])

    def test_the_source_is_kept_and_a_crop_in_place_works(self):
        before = self.source.read_bytes()
        pdfmd_crop.crop_pdf(self.source, self.dir / "other.pdf")
        self.assertEqual(self.source.read_bytes(), before)
        pdfmd_crop.crop_pdf(self.source, self.source, pad=0, page=2)
        self.assertEqual(media(self.source), [50.0, 30.0, 110.0, 50.0])
        self.assertEqual(list(self.dir.glob("*.part")), [])

    def test_a_foot_as_tall_as_the_page_is_refused(self):
        with self.assertRaises(pdfmd_crop.CropError):
            pdfmd_crop.crop_pdf(self.source, self.dir / "out.pdf", ignore_bottom=100)

    def test_not_a_pdf(self):
        text = self.dir / "text.pdf"
        text.write_text("not a pdf")
        with self.assertRaises(pdfmd_crop.CropError):
            pdfmd_crop.crop_pdf(text, self.dir / "out.pdf")


class NoGhostscript(unittest.TestCase):
    def test_it_says_what_to_install(self):
        with mock.patch.object(pdfmd_crop.shutil, "which", return_value=None):
            with self.assertRaises(pdfmd_crop.CropError) as raised:
                pdfmd_crop.ink_boxes(Path("x.pdf"))
        self.assertIn("Ghostscript", str(raised.exception))


@unittest.skipUnless(GS and PYPDF, "needs Ghostscript and pypdf")
class CommandLine(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="pdfmd-test-crop-")
        self.addCleanup(self.scratch.cleanup)
        self.dir = Path(self.scratch.name)
        self.source = self.dir / "formula.pdf"
        draw(self.source, "50 30 60 20 rectfill showpage")

    def run_pdfmd(self, *arguments: str):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, encoding="utf-8",
                              cwd=self.dir)

    def test_the_result_sits_beside_the_source(self):
        done = self.run_pdfmd("--crop", "formula.pdf", "--crop-pad", "1")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("formula-crop.pdf", done.stdout)
        self.assertEqual(media(self.dir / "formula-crop.pdf"), [49.0, 29.0, 111.0, 51.0])

    def test_o_names_a_file_or_a_folder(self):
        self.assertEqual(self.run_pdfmd("--crop", "formula.pdf", "-o", "tight.pdf").returncode, 0)
        self.assertTrue((self.dir / "tight.pdf").is_file())
        shutil.copy(self.source, self.dir / "second.pdf")
        done = self.run_pdfmd("--crop", "formula.pdf", "second.pdf", "-o", "out")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.dir / "out" / "second-crop.pdf").is_file())

    def test_a_missing_file_and_a_stray_option_fail(self):
        self.assertEqual(self.run_pdfmd("--crop", "nope.pdf").returncode, 1)
        stray = self.run_pdfmd("--crop-pad", "1", "formula.pdf")
        self.assertNotEqual(stray.returncode, 0)
        self.assertIn("go with --crop", stray.stderr)


if __name__ == "__main__":
    unittest.main()
