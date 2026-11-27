"""`pdfmd --crop` / pdfmd_crop: a PDF cut to what it draws. The pages are drawn by Ghostscript from PostScript, so the
ink is known exactly."""

from __future__ import annotations

import os
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

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

    @unittest.skipUnless(shutil.which("mutool"), "needs MuPDF")
    def test_mupdf_bbox_keeps_the_crop_origin_and_rotation(self):
        writer = pypdf.PdfWriter()
        page = writer.add_page(pypdf.PdfReader(str(self.source)).pages[0])
        page.rotate(90)
        source, target = self.dir / "rotated.pdf", self.dir / "out.pdf"
        writer.write(source)
        with mock.patch.object(pdfmd_crop, "ghostscript", return_value=None):
            pdfmd_crop.crop_pdf(source, target, pad=0, ignore_bottom=15)
        self.assertEqual(media(target), [50.0, 30.0, 110.0, 50.0])

    @unittest.skipUnless(shutil.which("pdftoppm"), "needs Poppler pdftoppm")
    def test_poppler_scan_measures_the_nonwhite_pixels_without_bbox_tools(self):
        target = self.dir / "out.pdf"
        pdftoppm = shutil.which("pdftoppm")
        with mock.patch.object(shutil, "which", side_effect=lambda name: pdftoppm if name == "pdftoppm" else None):
            pdfmd_crop.crop_pdf(self.source, target, pad=0, ignore_bottom=15, page=1)
        self.assertEqual(media(target), [50.0, 30.0, 110.0, 50.0])

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
        with mock.patch.object(shutil, "which", return_value=None):
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

    def test_crop_preserves_attachments_and_outline_for_every_destination(self):
        writer = pypdf.PdfWriter(clone_from=str(self.source))
        writer.add_attachment("source.md", b"# Original\n")
        writer.add_outline_item("Formula", 0)
        writer.add_metadata({"/Subject": "Keep me"})
        writer.write(str(self.source))
        for name in ("other.pdf", "formula.pdf"):
            with self.subTest(name=name):
                env = dict(os.environ, PDFMD_CONFIG="", PDFMD_NO_PROMPT="1")
                for key in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
                    env[key] = str(self.dir / key)
                done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"),
                                       "--crop", str(self.source), "-o", str(self.dir / name)],
                                      cwd=self.dir, env=env, stdin=subprocess.DEVNULL,
                                      capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr)
                reader = pypdf.PdfReader(str(self.dir / name))
                self.assertEqual(reader.attachments["source.md"], [b"# Original\n"])
                self.assertEqual(reader.outline[0].title, "Formula")
                self.assertEqual(reader.get_destination_page_number(reader.outline[0]), 0)
                self.assertEqual(reader.metadata.subject, "Keep me")
                self.assertEqual(media(self.dir / name), [48.0, 28.0, 112.0, 52.0])

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

    def run_pdfmd(self, *arguments: str, path: str | None = None, config: str | None = None):
        env = {**os.environ, "PDFMD_NO_PROMPT": "1"}
        if path is not None:
            env["PATH"] = path
        if config is not None:
            env["PDFMD_CONFIG"] = config
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

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "needs Pillow to inspect pixels")
    def test_background_changes_only_when_requested(self):
        from PIL import Image

        for target, colour, expected in (("png", None, (0, 0, 0, 0)), ("png", "#0a3296", (10, 50, 150, 255)),
                                         ("jpg", None, (255, 255, 255, 255)), ("jpg", "#0a3296", (10, 50, 150, 255))):
            with self.subTest(target=target, colour=colour):
                args = ("--image-background", colour) if colour else ()
                done = self.run_pdfmd("formula.pdf", "--crop", "--crop-page", "2", "--image-dpi", "72",
                                      "--crop-pad", "20", "--image-quality", "100", "-o", f"image.{target}", *args)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                with Image.open(self.dir / f"image.{target}") as image:
                    pixel = image.convert("RGBA").getpixel((1, 1))
                if colour is None and target == "png":
                    self.assertEqual(pixel[3], 0)
                elif target == "jpg":
                    for actual, wanted in zip(pixel, expected):
                        self.assertAlmostEqual(actual, wanted, delta=3)
                else:
                    self.assertEqual(pixel, expected)

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "needs Pillow to inspect WebP")
    def test_webp_supports_alpha_and_layered_background(self):
        from PIL import Image, features
        if not features.check("webp"):
            self.skipTest("needs Pillow with WebP support")
        config = self.dir / "config.yaml"
        config.write_text("options: {image-background: blue}\n", encoding="utf-8")
        for args, colour in (((), (0, 0, 255, 255)), (("--image-background", "transparent"), (0, 0, 0, 0))):
            with self.subTest(args=args):
                done = self.run_pdfmd("formula.pdf", "-o", "x.webp", "--image-dpi", "72", "--image-quality", "100",
                                      *args, config=str(config))
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                with Image.open(self.dir / "x" / "001.webp") as image:
                    self.assertEqual(image.format, "WEBP")
                    self.assertEqual(image.size, (200, 100))
                    pixel = image.convert("RGBA").getpixel((0, 0))
                    self.assertEqual(pixel[3], colour[3])
                    if colour[3]:
                        for actual, wanted in zip(pixel[:3], colour[:3]):
                            self.assertAlmostEqual(actual, wanted, delta=2)

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

    def test_several_targets_need_a_folder_for_o(self):
        done = self.run_pdfmd("formula.pdf", "--crop", "--to", "png,pdf", "-o", "x.png")
        self.assertEqual(done.returncode, 1)
        self.assertIn("names a folder", done.stderr)
        done = self.run_pdfmd("formula.pdf", "--to", "png,docx", "-o", "x.docx")
        self.assertEqual(done.returncode, 1)
        self.assertIn("names a folder", done.stderr)
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

    def test_default_output_list_and_finish_use_the_same_pdf(self):
        (self.dir / "note.md").write_text(
            "---\npdfmd-options:\n  default-output: [PNG, pdf]\n  crop: true\n"
            "  crop-page: 2\n  crop-pad: 5\n  image-dpi: 72\n---\n\nFirst\n\n\\newpage\n\nSecond\n",
            encoding="utf-8",
        )
        done = self.run_pdfmd("note.md", "-e", "inkmd", "--no-stamp", "--no-backup", path=self.native_path())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        pdf = self.dir / "note.pdf"
        self.assertEqual(len(pypdf.PdfReader(str(pdf)).pages), 1)
        left, bottom, right, top = media(pdf)
        width, height = png_size(self.dir / "note.png")
        self.assertAlmostEqual(width, right - left, delta=1)
        self.assertAlmostEqual(height, top - bottom, delta=1)

    def test_picture_settings_follow_metadata_and_cli(self):
        (self.dir / "note.md").write_text("First\n\n\\newpage\n\nSecond\n", encoding="utf-8")
        (self.dir / "metadata.yaml").write_text(
            "pdfmd-options: {image-dpi: 36, page-folder: false, image-quality: 75}\n", encoding="utf-8",
        )
        config = self.dir / "config.yaml"
        config.write_text("options: {image-dpi: 144, page-folder: true, image-quality: 0}\n", encoding="utf-8")
        done = self.run_pdfmd("note.md", "-e", "inkmd", "-t", "jpg,png", "-y", "metadata.yaml",
                              "--image-dpi", "72", "--no-backup", config=str(config), path=self.native_path())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(png_size(self.dir / "note-001.png"), (595, 842))
        self.assertTrue((self.dir / "note-002.jpg").is_file())
        self.assertFalse((self.dir / "note.pdf").exists())
        done = self.run_pdfmd("note.md", "-e", "inkmd", "-t", "png", "-y", "metadata.yaml",
                              "--page-folder", "--no-backup", config=str(config), path=self.native_path())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(png_size(self.dir / "note" / "001.png"), (298, 421))

    def test_standalone_crop_uses_config_padding_page_and_bottom(self):
        config = self.dir / "config.yaml"
        config.write_text("options: {crop-pad: 0, crop-page: 1, crop-ignore-bottom: 20}\n", encoding="utf-8")
        done = self.run_pdfmd("formula.pdf", "--crop", config=str(config))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        cropped = self.dir / "formula-crop.pdf"
        self.assertEqual(len(pypdf.PdfReader(str(cropped)).pages), 1)
        self.assertEqual(media(cropped), [50.0, 30.0, 110.0, 50.0])

    def test_batch_folder_defaults_apply_to_each_pdf_and_picture(self):
        source = self.dir / "notes"
        source.mkdir()
        for name in ("a.md", "b.md"):
            (source / name).write_text("First\n\n\\newpage\n\nSecond\n", encoding="utf-8")
        layer = source / ".pdfmd"
        layer.mkdir()
        (layer / "config.yaml").write_text(
            "options: {default-output: 'png, pdf', page-folder: off, image-dpi: 72}\n", encoding="utf-8",
        )
        done = self.run_pdfmd("notes", "-b", "-j", "2", "-e", "inkmd", "-o", "out", path=self.native_path())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        for name in ("a", "b"):
            self.assertTrue((self.dir / "out" / f"{name}.pdf").is_file())
            self.assertEqual(png_size(self.dir / "out" / f"{name}-002.png"), (595, 842))

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_default_formats_can_include_a_separate_writer(self):
        (self.dir / "note.md").write_text(
            "---\npdfmd-options: {default-output: [html, PNG, pdf]}\n---\n\nHello\n", encoding="utf-8",
        )
        done = self.run_pdfmd("note.md", "-e", "inkmd", "-o", "out")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(sorted(path.name for path in (self.dir / "out").iterdir()), ["note.html", "note.pdf", "note.png"])

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_a_format_that_is_not_a_picture_is_a_run_of_its_own(self):
        (self.dir / "note.md").write_text("# T\n\ntext\n", encoding="utf-8")
        done = self.run_pdfmd("note.md", "--to", "html,png", "--crop", "--crop-ignore-bottom", "60", "--image-dpi", "30", "-o", "out", "-e", "inkmd",
                              path=os.environ.get("PATH", "") + os.pathsep + str(Path(GS).parent))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(sorted(path.name for path in (self.dir / "out").iterdir()), ["note.html", "note.png"])

    def test_svg(self):
        if not (shutil.which("pdftocairo") or shutil.which("mutool")):
            self.skipTest("needs pdftocairo or mutool")
        done = self.run_pdfmd("formula.pdf", "--crop", "--crop-page", "1", "--to", "svg")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("<svg", (self.dir / "formula.svg").read_text())

    @unittest.skipUnless(shutil.which("pdftocairo"), "needs Poppler pdftocairo")
    def test_png_falls_back_when_ghostscript_fails(self):
        from pdfmd_crop import images
        pdftocairo = shutil.which("pdftocairo")
        target = self.dir / "page.png"
        with (mock.patch.object(images, "ghostscript", return_value=str(self.dir / "missing-gs")),
              mock.patch.object(shutil, "which", side_effect=lambda name: pdftocairo if name == "pdftocairo" else None)):
            made = images.pictures(self.source, target, "png", 72, folder=False)
        self.assertEqual([png_size(path) for path in made], [(200, 100), (200, 100)])

    def test_a_target_without_pages_is_refused_before_anything_is_built(self):
        done = self.run_pdfmd("formula.pdf", "--crop", "--to", "html")
        self.assertEqual(done.returncode, 1)
        self.assertIn("pdf, png, jpg, tiff, eps, ps, svg or webp", done.stderr)
        self.assertEqual(sorted(path.name for path in self.dir.iterdir() if path.suffix != ".ps"), ["formula.pdf"])

    def test_standalone_cropped_office_pages_have_their_own_sizes(self):
        for target in ("docx", "odt"):
            with self.subTest(target=target):
                done = self.run_pdfmd("formula.pdf", "--crop", "--crop-pad", "0", "--image-dpi", "72", "-t", target)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                with zipfile.ZipFile(self.dir / f"formula.{target}") as archive:
                    if target == "docx":
                        word = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                        document = ElementTree.fromstring(archive.read("word/document.xml"))
                        sizes = [(int(node.attrib[word + "w"]), int(node.attrib[word + "h"]))
                                 for node in document.iter(word + "pgSz")]
                        self.assertEqual(len(sizes), 2)
                        for actual, expected in zip(sizes, [(1200, 400), (400, 400)]):
                            self.assertAlmostEqual(actual[0], expected[0], delta=1)
                            self.assertAlmostEqual(actual[1], expected[1], delta=1)
                        prefix = "word/media"
                    else:
                        style = "{urn:oasis:names:tc:opendocument:xmlns:style:1.0}"
                        fo = "{urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0}"
                        styles = ElementTree.fromstring(archive.read("styles.xml"))
                        sizes = [(float(node.attrib[fo + "page-width"][:-2]), float(node.attrib[fo + "page-height"][:-2]))
                                 for node in styles.iter(style + "page-layout-properties")]
                        self.assertEqual(len(sizes), 2)
                        for actual, expected in zip(sizes, [(60, 20), (20, 20)]):
                            self.assertAlmostEqual(actual[0], expected[0], delta=0.1)
                            self.assertAlmostEqual(actual[1], expected[1], delta=0.1)
                        prefix = "Pictures"
                    for index, size in enumerate(((60, 20), (20, 20)), 1):
                        data = archive.read(f"{prefix}/page-{index}.png")
                        self.assertEqual((int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")), size)
                        if shutil.which("pdftocairo") or shutil.which("mutool"):
                            self.assertIn(b"<svg", archive.read(f"{prefix}/page-{index}.svg"))

    def test_source_crop_and_office_outputs_share_the_pdf(self):
        document = self.dir / "note.md"
        document.write_text(
            "---\npdfmd-options: {default-output: [docx, pdf, odt], crop: true, crop-page: 2}\n---\n"
            "\nFirst\n\n\\newpage\n\nSecond\n", encoding="utf-8",
        )
        done = self.run_pdfmd("note.md", "-e", "inkmd", "--no-stamp", "--no-backup", path=self.native_path())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        pdf = self.dir / "note.pdf"
        self.assertEqual(len(pypdf.PdfReader(str(pdf)).pages), 1)
        left, bottom, right, top = media(pdf)
        for target, entry in (("docx", "word/media/page-1.png"), ("odt", "Pictures/page-1.png")):
            with zipfile.ZipFile(self.dir / f"note.{target}") as archive:
                data = archive.read(entry)
                self.assertNotIn(entry.replace("-1.", "-2."), archive.namelist())
                self.assertAlmostEqual(int.from_bytes(data[16:20], "big"), (right - left) * 300 / 72, delta=2)
                self.assertAlmostEqual(int.from_bytes(data[20:24], "big"), (top - bottom) * 300 / 72, delta=2)

    def test_cropped_office_uses_png_when_vector_export_fails(self):
        from pdfmd_crop import rendering
        from pdfmd_office.cropped import write

        targets = {kind: self.dir / f"fallback.{kind}" for kind in ("docx", "odt")}
        with mock.patch.object(rendering, "svg", side_effect=pdfmd_crop.CropError("no vector converter")):
            self.assertEqual(write(self.source, targets, 72, None), list(targets.values()))
        for kind, prefix in (("docx", "word/media"), ("odt", "Pictures")):
            with zipfile.ZipFile(targets[kind]) as archive:
                assets = sorted(name for name in archive.namelist() if name.startswith(f"{prefix}/"))
                self.assertEqual(assets, [f"{prefix}/page-1.png", f"{prefix}/page-2.png"])

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_no_crop_keeps_the_editable_word_writer(self):
        (self.dir / "note.md").write_text(
            "---\npdfmd-options: {crop: true}\n---\n\nEditable word.\n", encoding="utf-8",
        )
        done = self.run_pdfmd("note.md", "-t", "docx,pdf", "--no-crop", "-e", "inkmd")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        with zipfile.ZipFile(self.dir / "note.docx") as archive:
            self.assertIn(b"Editable word.", archive.read("word/document.xml"))

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

    @unittest.skipUnless(shutil.which("pandoc") and shutil.which("typst"), "needs Pandoc and Typst")
    def test_a_report_is_one_result_named_after_its_folder(self):
        folder = self.dir / "rep"
        folder.mkdir()
        for name in ("01-a", "02-b"):
            (folder / f"{name}.md").write_text(f"# {name}\n\ntext\n", encoding="utf-8")
        done = self.run_pdfmd("rep", "-r", "--crop", "--crop-ignore-bottom", "60", "--to", "png", "-e", "typst")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((folder / "rep.png").is_file() or (folder / "rep" / "001.png").is_file())

    def test_a_dpi_without_a_picture_is_refused(self):
        self.assertNotEqual(self.run_pdfmd("formula.pdf", "--image-dpi", "100").returncode, 0)

    @unittest.skipUnless(shutil.which("pandoc") and shutil.which("typst"), "needs Pandoc and Typst")
    def test_markdown_crop_ignores_the_engine_number_unless_requested(self):
        document = self.dir / "note.md"
        output = self.dir / "out"
        output.mkdir()
        for flags, options, numbered in (
            (("--crop",), "{}", False),
            (("--crop", "--page-numbers"), "{}", True),
            (("--crop", "-V", "page-numbering=1"), "{}", True),
            ((), "{crop: true}", False),
            ((), "{crop: true, page-numbers: on}", True),
            (("--crop", "-t", "png,pdf"), "{}", False),
            (("--crop", "-t", "png,pdf"), "{page-numbers: on}", True),
        ):
            with self.subTest(flags=flags, options=options):
                document.write_text(f"---\npage-numbering: '1'\npdfmd-options: {options}\n---\n\nOne synthetic line.\n",
                                    encoding="utf-8")
                done = self.run_pdfmd("note.md", "-e", "typst", "-o", "out", "--no-stamp", *flags)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                _, bottom, _, top = media(output / "note.pdf")
                self.assertEqual(top - bottom > 100, numbered, (bottom, top))

    def test_a_markdown_source_is_built_then_cropped(self):
        # no Pandoc on the path: the built-in renderer makes the PDF, so the test needs no engine
        (self.dir / "note.md").write_text("# Title\n\nA line of text.\n", encoding="utf-8")
        path = str(Path(GS).parent) + os.pathsep + "/usr/bin" + os.pathsep + "/bin"
        done = self.run_pdfmd("note.md", "--crop", "--crop-pad", "0", "--crop-ignore-bottom", "60", path=path)   # the page number is in the foot
        self.assertEqual(done.returncode, 0, done.stderr)
        box = media(self.dir / "note.pdf")
        self.assertLess(box[3] - box[1], 100)   # two lines of text, not the page
        self.assertEqual(sorted(path.name for path in self.dir.glob("note*")), ["note.md", "note.pdf"])

    def test_crop_is_a_build_mode_with_automatic_source_lookup(self):
        (self.dir / "only.md").write_text("An automatic build.\n", encoding="utf-8")
        done = self.run_pdfmd("--crop", "--crop-ignore-bottom", "60", "-e", "inkmd", "--no-stamp", "--no-backup",
                              path=self.native_path())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        box = media(self.dir / "only.pdf")
        self.assertLess(box[3] - box[1], 100)

    def test_crop_settings_follow_layers_and_the_cli_can_turn_them_off(self):
        document = self.dir / "note.md"
        document.write_text("One line.\n", encoding="utf-8")
        config = self.dir / "config.yaml"
        config.write_text("options: {crop: true}\n", encoding="utf-8")
        done = self.run_pdfmd("note.md", "-e", "inkmd", "-o", "global.pdf", "--no-stamp", "--no-backup",
                              "--crop-ignore-bottom", "60", path=self.native_path(), config=str(config))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        box = media(self.dir / "global.pdf")
        self.assertLess(box[3] - box[1], 100, box)
        folder = self.dir / ".pdfmd"
        folder.mkdir()
        (folder / "config.yaml").write_text("options: {crop: false}\n", encoding="utf-8")
        metadata = self.dir / "metadata.yaml"
        metadata.write_text("pdfmd-options: {crop: true}\n", encoding="utf-8")
        variants = [
            ("folder.pdf", ("-y",), False),
            ("metadata.pdf", ("-y", "metadata.yaml", "--crop-ignore-bottom", "60"), True),
            ("off.pdf", ("--no-crop",), False),
        ]
        for name, arguments, cropped in variants:
            with self.subTest(name=name):
                done = self.run_pdfmd("note.md", "-e", "inkmd", "-o", name, "--no-stamp", "--no-backup", *arguments,
                                      path=self.native_path(), config=str(config))
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                box = media(self.dir / name)
                self.assertEqual(box[3] - box[1] < 100, cropped, box)
        document.write_text("---\npdfmd-options: {crop: false}\n---\n\nOne line.\n", encoding="utf-8")
        done = self.run_pdfmd("note.md", "-e", "inkmd", "-y", "metadata.yaml", "-o", "front.pdf", "--no-stamp", "--no-backup",
                              path=self.native_path(), config=str(config))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        box = media(self.dir / "front.pdf")
        self.assertGreater(box[3] - box[1], 600)

    def test_a_failed_build_crop_preserves_the_existing_pdf(self):
        document = self.dir / "note.md"
        document.write_text("Only one page.\n", encoding="utf-8")
        before = document.read_bytes()
        previous = self.source.read_bytes()
        done = self.run_pdfmd("note.md", "-e", "inkmd", "--crop", "--crop-page", "3", "--rewrite",
                              "-o", "formula.pdf", path=self.native_path())
        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("not a page 3", done.stdout + done.stderr)
        self.assertEqual(self.source.read_bytes(), previous)
        self.assertEqual(document.read_bytes(), before)

        picture = self.run_pdfmd("note.md", "-e", "inkmd", "--crop", "--crop-page", "3", "--to", "png",
                                 path=self.native_path())
        self.assertNotEqual(picture.returncode, 0, picture.stdout + picture.stderr)
        self.assertIn("not a page 3", picture.stderr)
        self.assertFalse((self.dir / "note.png").exists())


if __name__ == "__main__":
    unittest.main()
