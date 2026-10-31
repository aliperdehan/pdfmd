"""`pdfmd --crop` / pdfmd_crop: a PDF cut to what it draws. The pages are drawn by Ghostscript from PostScript, so the
ink is known exactly."""

from __future__ import annotations

import os
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


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


@unittest.skipUnless(GS and PYPDF, "needs Ghostscript and pypdf")
class Pictures(unittest.TestCase):
    """`--to png|svg`, with and without `--crop`, from a PDF and from a Markdown source."""

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="pdfmd-test-crop-")
        self.addCleanup(self.scratch.cleanup)
        self.dir = Path(self.scratch.name)
        self.source = self.dir / "formula.pdf"
        draw(self.source, "50 30 60 20 rectfill showpage 10 10 20 20 rectfill showpage")

    def run_pdfmd(self, *arguments: str, path: str | None = None):
        env = None if path is None else {"PATH": path}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, encoding="utf-8",
                              cwd=self.dir, env=env)

    def test_png_without_crop_is_the_whole_page_one_file_per_page(self):
        done = self.run_pdfmd("formula.pdf", "--to", "png", "--image-dpi", "72")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(png_size(self.dir / "formula" / "001.png"), (200, 100))
        self.assertTrue((self.dir / "formula" / "002.png").is_file())
        self.assertFalse((self.dir / "formula.png").exists())
        self.assertIn("2 pages", done.stderr)

    def test_png_with_crop_is_the_ink_and_one_page_gets_the_plain_name(self):
        done = self.run_pdfmd("formula.pdf", "--crop", "--crop-page", "1", "--crop-pad", "0", "--to", "png", "--image-dpi", "72")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(png_size(self.dir / "formula.png"), (60, 20))

    def test_o_with_a_png_suffix_chooses_the_format(self):
        done = self.run_pdfmd("formula.pdf", "--crop", "--crop-page", "2", "-o", "tight.png", "--image-dpi", "72")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(png_size(self.dir / "tight.png"), (24, 24))   # 20 pt of ink and 2 pt of pad each side

    def test_jpeg_is_white_and_takes_a_quality(self):
        done = self.run_pdfmd("formula.pdf", "--crop", "--crop-page", "1", "--crop-pad", "0", "--to", "jpeg", "--image-dpi", "72")
        self.assertEqual(done.returncode, 0, done.stderr)
        data = (self.dir / "formula.jpg").read_bytes()
        self.assertEqual(data[:2], b"\xff\xd8")
        self.assertEqual(self.run_pdfmd("formula.pdf", "--to", "jpg", "--image-quality", "0").returncode, 1)
        self.assertEqual(self.run_pdfmd("formula.pdf", "--crop", "-o", "x.jpeg", "--crop-page", "1").returncode, 0)
        self.assertTrue((self.dir / "x.jpeg").is_file())

    def test_tiff_and_postscript_hold_all_pages_in_one_file_and_eps_one_each(self):
        for target, magic in (("tiff", (b"II*\x00", b"MM\x00*")), ("ps", (b"%!PS",))):
            done = self.run_pdfmd("formula.pdf", "--to", target, "--image-dpi", "72")
            self.assertEqual(done.returncode, 0, done.stderr)
            data = (self.dir / f"formula.{target}").read_bytes()
            self.assertTrue(data.startswith(magic), target)
        done = self.run_pdfmd("formula.pdf", "--crop", "--to", "eps")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(b"EPSF", (self.dir / "formula" / "001.eps").read_bytes()[:40])
        self.assertTrue((self.dir / "formula" / "002.eps").is_file())
        self.assertEqual(self.run_pdfmd("formula.pdf", "--crop", "--to", "tif", "-o", "x.tif", "--crop-page", "1").returncode, 0)
        self.assertTrue((self.dir / "x.tif").is_file())

    def test_several_targets_come_from_one_build_and_sit_beside_each_other(self):
        done = self.run_pdfmd("formula.pdf", "--crop", "--crop-page", "1", "--to", "png,jpeg,pdf", "--image-dpi", "72")
        self.assertEqual(done.returncode, 0, done.stderr)
        for name in ("formula.png", "formula.jpg", "formula-crop.pdf"):
            self.assertTrue((self.dir / name).is_file(), name)
        (self.dir / "note.md").write_text("# T\n\ntext\n", encoding="utf-8")
        done = self.run_pdfmd("note.md", "--crop", "--crop-ignore-bottom", "60", "--to", "pdf,png", path=self.native_path())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.dir / "note.pdf").is_file() and (self.dir / "note.png").is_file())

    def test_several_targets_need_a_folder_for_o_and_only_picture_formats(self):
        done = self.run_pdfmd("formula.pdf", "--crop", "--to", "png,pdf", "-o", "x.png")
        self.assertEqual(done.returncode, 1)
        self.assertIn("names a folder", done.stderr)
        done = self.run_pdfmd("formula.pdf", "--to", "png,docx")
        self.assertEqual(done.returncode, 1)
        self.assertIn("a run of its own", done.stderr)
        done = self.run_pdfmd("formula.pdf", "--to", "pdf,png", "--image-dpi", "72")   # a PDF to pdf without a crop: nothing to write
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("PDF already", done.stderr)
        self.assertFalse((self.dir / "formula-crop.pdf").exists())

    def test_the_pages_can_sit_beside_the_document_instead_of_in_a_folder(self):
        done = self.run_pdfmd("formula.pdf", "--to", "png", "--image-dpi", "30", "--no-page-folder")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.dir / "formula-001.png").is_file() and (self.dir / "formula-002.png").is_file())
        self.assertFalse((self.dir / "formula").exists())
        self.assertIn("beside it", done.stderr)

    def test_the_folder_switch_is_an_option_of_the_document_and_of_the_folder_layers(self):
        text = "---\npdfmd-options:\n  page-folder: false\n---\n\npage one\n\n\\newpage\n\npage two\n"
        (self.dir / "doc.md").write_text(text, encoding="utf-8")
        done = self.run_pdfmd("doc.md", "--to", "png", "--image-dpi", "30", path=self.native_path())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.dir / "doc-001.png").is_file(), done.stderr)
        done = self.run_pdfmd("doc.md", "--to", "png", "--image-dpi", "30", "--page-folder", path=self.native_path())   # the flag wins
        self.assertTrue((self.dir / "doc" / "001.png").is_file(), done.stderr)

    def test_svg(self):
        if not (shutil.which("pdftocairo") or shutil.which("mutool")):
            self.skipTest("needs pdftocairo or mutool")
        done = self.run_pdfmd("formula.pdf", "--crop", "--crop-page", "1", "--to", "svg")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("<svg", (self.dir / "formula.svg").read_text())

    def test_a_target_without_pages_is_refused_before_anything_is_built(self):
        done = self.run_pdfmd("formula.pdf", "--crop", "--to", "docx")
        self.assertEqual(done.returncode, 1)
        self.assertIn("pdf, png, jpg, tiff, eps, ps or svg", done.stderr)
        self.assertEqual(sorted(path.name for path in self.dir.iterdir() if path.suffix != ".ps"), ["formula.pdf"])

    def native_path(self) -> str:
        return str(Path(GS).parent) + os.pathsep + "/usr/bin" + os.pathsep + "/bin"

    def test_batch_crops_every_markdown_file_of_a_folder_into_o(self):
        folder = self.dir / "notes"
        folder.mkdir()
        for name in ("a", "b"):
            (folder / f"{name}.md").write_text(f"# {name}\n\ntext\n", encoding="utf-8")
        done = self.run_pdfmd("notes", "-b", "--crop", "--crop-ignore-bottom", "60", "-o", "out", "-j", "2", path=self.native_path())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(sorted(path.name for path in (self.dir / "out").iterdir()), ["a.pdf", "b.pdf"])
        box = media(self.dir / "out" / "a.pdf")
        self.assertLess(box[3] - box[1], 100)

    def test_batch_needs_one_folder(self):
        self.assertEqual(self.run_pdfmd("-b", "--crop", "formula.pdf").returncode, 1)

    def test_a_report_is_one_result_named_after_its_folder(self):
        folder = self.dir / "rep"
        folder.mkdir()
        for name in ("01-a", "02-b"):
            (folder / f"{name}.md").write_text(f"# {name}\n\ntext\n", encoding="utf-8")
        done = self.run_pdfmd("rep", "-r", "--crop", "--crop-ignore-bottom", "60", "--to", "png", path=self.native_path())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((folder / "rep.png").is_file() or (folder / "rep" / "001.png").is_file())

    def test_a_dpi_without_a_picture_is_refused(self):
        self.assertNotEqual(self.run_pdfmd("formula.pdf", "--image-dpi", "100").returncode, 0)

    def test_a_markdown_source_is_built_then_cropped(self):
        # no Pandoc on the path: the built-in renderer makes the PDF, so the test needs no engine
        (self.dir / "note.md").write_text("# Title\n\nA line of text.\n", encoding="utf-8")
        path = str(Path(GS).parent) + os.pathsep + "/usr/bin" + os.pathsep + "/bin"
        done = self.run_pdfmd("note.md", "--crop", "--crop-pad", "0", "--crop-ignore-bottom", "60", path=path)   # the page number is in the foot
        self.assertEqual(done.returncode, 0, done.stderr)
        box = media(self.dir / "note.pdf")
        self.assertLess(box[3] - box[1], 100)   # two lines of text, not the page
        self.assertEqual(sorted(path.name for path in self.dir.glob("note*")), ["note.md", "note.pdf"])


if __name__ == "__main__":
    unittest.main()
