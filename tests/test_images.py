"""SVG for LaTeX engines (pdfmd_images, pdfmd_lua/images.lua) and the graphicx a raw \\includegraphics needs."""

from __future__ import annotations

import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from cache_support import cache_env  # noqa: E402

import pdfmd  # noqa: E402
import pdfmd_images as images  # noqa: E402

PANDOC = shutil.which("pandoc")
SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">'
       '<rect width="200" height="100" fill="#cde"/><circle cx="50" cy="50" r="30" fill="#c33"/></svg>')
PNG_BYTES = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478"
                          "9c6360606060000000050001a5f645400000000049454e44ae426082")


def fake(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


class Scan(unittest.TestCase):
    def test_every_kind_is_found_and_code_comments_and_front_matter_are_not(self):
        text = ("---\ntitle: T\nheader-includes: '![x](front.svg)'\n---\n\n![a](one.svg){width=2cm}\n"
                '![b](<two words.svg> "a title")\n\n```\n![code](code.svg)\n```\n\n<!--\n![c](comment.svg)\n-->\n'
                "\\includegraphics[width=3cm]{three.svg} and \\includesvg{four} \\includesvg[inkscapelatex=false]{five}\n"
                "![remote](https://example.com/x.svg)\n")
        found = images.find_references(text)
        self.assertEqual([(item.kind, item.path) for item in found],
                         [("markdown", "one.svg"), ("markdown", "two%20words.svg"), ("graphics", "three.svg"),
                          ("includesvg", "four"), ("includesvg", "five"), ("markdown", "https://example.com/x.svg")])
        self.assertTrue(all(item.is_svg for item in found))
        self.assertTrue(found[-1].remote)
        self.assertFalse(found[0].remote)

    def test_balanced_and_reference_image_destinations(self):
        text = '![plot](plot(1).svg) ![remote][ P ] ![short][] ![shortcut]\n\n[p]: https://example.test/plot.svg\n[short]: short.svg\n[shortcut]: <other plot.svg>\n'
        found = images.find_references(text)
        self.assertEqual([item.path for item in found],
                         ["plot(1).svg", "https://example.test/plot.svg", "short.svg", "other%20plot.svg"])
        self.assertEqual([item.line for item in found], [1, 1, 1, 1])

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_nested_alt_and_multiline_reference_match_pandoc(self):
        import json
        text = "![a [b] c](x.png)\n\n![ref][id]\n\n[id]:\n  y.png\n"
        parsed = json.loads(subprocess.run([PANDOC, "-f", "markdown", "-t", "json"], input=text,
                                           capture_output=True, text=True, check=True).stdout)
        def destinations(node):
            if isinstance(node, dict):
                if node.get("t") == "Image":
                    return [node["c"][2][0]]
                return [item for value in node.values() for item in destinations(value)]
            if isinstance(node, list):
                return [item for value in node for item in destinations(value)]
            return []
        self.assertEqual([item.path for item in images.find_references(text)], destinations(parsed))

    def test_a_raster_is_not_an_svg(self):
        [item] = images.find_references("![p](photo.PNG)")
        self.assertFalse(item.is_svg)

    @unittest.skipUnless(PANDOC and os.name != "nt", "needs Pandoc and symlinks")
    def test_checkout_converts_both_svg_references(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bindir = root / "bin"
            bindir.mkdir()
            (bindir / "pandoc").symlink_to(PANDOC)
            fake(bindir, "inkscape", 'for a; do case "$a" in --export-filename=*) printf "%%PDF-1.4" > "${a#--export-filename=}";; esac; done')
            (root / "x.svg").write_text(SVG, encoding="utf-8")
            (root / "y.svg").write_text(SVG.replace("#c33", "#c34"), encoding="utf-8")
            (root / "doc.md").write_text("![a [b] c](x.svg)\n\n![ref][id]\n\n[id]:\n  y.svg\n", encoding="utf-8")
            env = {**os.environ, "PATH": str(bindir) + os.pathsep + "/usr/bin:/bin", "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                   "XDG_CONFIG_HOME": str(root / "config"), "XDG_CACHE_HOME": str(root / "cache"), "XDG_DATA_HOME": str(root / "data")}
            done = subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), "doc.md", "--to", "latex", "-o", "out.tex", "--verbose"],
                                  cwd=root, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            maps = list((root / "cache").rglob("maps/*.yaml"))
            self.assertEqual(len(maps), 1, done.stdout + done.stderr)
            contents = maps[0].read_text(encoding="utf-8")
            self.assertIn("x.svg", contents)
            self.assertIn("y.svg", contents)


@unittest.skipIf(os.name == "nt", "the stand-in programs are sh scripts")
class Converting(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-images-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.svg = self.directory / "a.svg"
        self.svg.write_text(SVG, encoding="utf-8")
        self.bin = self.directory / "bin"
        self.bin.mkdir()
        self.cache = self.directory / "cache"
        self.which = lambda name: str(self.bin / name) if (self.bin / name).exists() else None

    def test_a_conversion_is_kept_by_content_and_reused(self):
        calls = self.directory / "calls"
        fake(self.bin, "rsvg-convert", f'echo x >> "{calls}"; while [ $# -gt 0 ]; do [ "$1" = -o ] && out="$2"; shift; done; printf %%PDF-1.4 > "$out"')
        with mock.patch("pdfmd_images.svg._python_module", return_value=False):
            first, why = images.convert_svg(self.svg, self.cache, self.which)
            second, _ = images.convert_svg(self.svg, self.cache, self.which)
            self.assertEqual((first, why), (second, ""))
            self.assertEqual(calls.read_text().count("x"), 1)               # converted once
            self.svg.write_text(SVG.replace("#c33", "#3c3"), encoding="utf-8")
            third, _ = images.convert_svg(self.svg, self.cache, self.which)
            self.assertNotEqual(first, third)                              # edited: converted again
            self.assertEqual(calls.read_text().count("x"), 2)

    def test_the_next_converter_is_tried_when_one_fails(self):
        fake(self.bin, "rsvg-convert", "echo bad drawing >&2; exit 1")
        fake(self.bin, "inkscape", 'for a; do case "$a" in --export-filename=*) printf %%PDF-1.4 > "${a#--export-filename=}";; esac; done')
        with mock.patch("pdfmd_images.svg._python_module", return_value=False):
            pdf, why = images.convert_svg(self.svg, self.cache, self.which)
        self.assertIsNotNone(pdf, why)

    def test_cached_raster_does_not_hide_a_new_vector_converter(self):
        from pdfmd_images import svg
        self.cache.mkdir()
        pdf = self.cache / svg.cache_name(self.svg)
        png = pdf.with_name(pdf.stem + "-192.png")
        png.write_bytes(PNG_BYTES)
        def convert(name, source, produced, *args, **kwargs):
            produced.write_bytes(b"%PDF-vector")
            return True, ""
        with mock.patch.object(svg, "available_converters", return_value=["typst", "resvg"]), \
                mock.patch.object(svg, "_run", side_effect=convert) as run:
            self.assertEqual(svg.convert_svg(self.svg, self.cache), (pdf, ""))
            self.assertEqual(run.call_args.args[0], "typst")
        with mock.patch.object(svg, "available_converters") as available, mock.patch.object(svg, "_run") as run:
            self.assertEqual(svg.convert_svg(self.svg, self.cache), (pdf, ""))
            available.assert_not_called()
            run.assert_not_called()

    def test_cached_raster_is_reused_without_vector_success(self):
        from pdfmd_images import svg
        self.cache.mkdir()
        pdf = self.cache / svg.cache_name(self.svg)
        png = pdf.with_name(pdf.stem + "-192.png")
        png.write_bytes(PNG_BYTES)
        for converters in ([], ["resvg"], ["typst", "resvg"]):
            with self.subTest(converters=converters), \
                    mock.patch.object(svg, "available_converters", return_value=converters), \
                    mock.patch.object(svg, "_run", return_value=(False, "bad SVG")) as run:
                self.assertEqual(svg.convert_svg(self.svg, self.cache), (png, ""))
                self.assertEqual(run.call_count, int("typst" in converters))

    def test_raster_fallback_records_failed_vector_converters(self):
        from pdfmd_images import svg
        def convert(name, source, produced, *args, **kwargs):
            if name == "resvg":
                produced.write_bytes(PNG_BYTES)
                return True, ""
            return False, "bad SVG"
        with mock.patch.object(svg, "available_converters", return_value=["soffice", "resvg"]), \
                mock.patch.object(svg, "_run", side_effect=convert) as run:
            png, why = svg.convert_svg(self.svg, self.cache)
            self.assertEqual(png.suffix, ".png", why)
            self.assertEqual(run.call_count, 2)
            run.reset_mock()
            self.assertEqual(svg.convert_svg(self.svg, self.cache), (png, ""))
            run.assert_not_called()
        def vector(name, source, produced, *args, **kwargs):
            produced.write_bytes(b"%PDF-vector")
            return True, ""
        with mock.patch.object(svg, "available_converters", return_value=["inkscape", "soffice", "resvg"]), \
                mock.patch.object(svg, "_run", side_effect=vector) as run:
            pdf, why = svg.convert_svg(self.svg, self.cache)
            self.assertEqual(pdf.suffix, ".pdf", why)
            self.assertEqual([call.args[0] for call in run.call_args_list], ["inkscape"])
            run.reset_mock()
            self.assertEqual(svg.convert_svg(self.svg, self.cache), (pdf, ""))
            run.assert_not_called()

    def test_legacy_or_invalid_raster_record_retries_available_tools_only_once(self):
        from pdfmd_images import svg
        self.cache.mkdir()
        pdf = self.cache / svg.cache_name(self.svg)
        png = pdf.with_name(pdf.stem + "-192.png")
        png.write_bytes(PNG_BYTES)
        record = png.with_suffix(".json")
        for content in (None, "broken JSON", '{"available": "typst"}'):
            if content is not None:
                record.write_text(content, encoding="utf-8")
            with self.subTest(content=content), \
                    mock.patch.object(svg, "available_converters", return_value=["typst", "resvg"]), \
                    mock.patch.object(svg, "_run", return_value=(False, "bad SVG")) as run:
                self.assertEqual(svg.convert_svg(self.svg, self.cache), (png, ""))
                self.assertEqual(svg.convert_svg(self.svg, self.cache), (png, ""))
                self.assertEqual(run.call_count, 1)

    def test_nothing_installed_says_what_to_install(self):
        with mock.patch("pdfmd_images.svg._python_module", return_value=False):
            pdf, why = images.convert_svg(self.svg, self.cache, self.which)
        self.assertIsNone(pdf)
        self.assertIn("rsvg", why)
        self.assertIn("typst", why)
        self.assertIn("resvg", why)

    def test_all_found_converters_keep_the_legacy_order(self):
        from pdfmd_images import svg
        with mock.patch.object(svg, "_python_module", return_value=True):
            self.assertEqual(svg.available_converters(lambda name: "/tools/" + name, lambda: "/tools/soffice"),
                             list(svg.CONVERTERS))

    def test_typst_sizes_the_page_and_uses_the_font_path_for_pdf_and_png(self):
        from pdfmd_images import svg
        fonts = self.directory / "fonts"
        fonts.mkdir()
        seen = []
        def run(command, **kwargs):
            seen.append(command)
            document = Path(command[-2]).read_text()
            self.assertIn("#set page(width: auto, height: auto, margin: 0pt)", document)
            self.assertIn("#image(", document)
            self.assertEqual(command[command.index("--font-path") + 1], str(fonts))
            self.assertIn("--root", command)
            Path(command[-1]).write_bytes(PNG_BYTES if "png" in command else b"%PDF-vector")
            return subprocess.CompletedProcess(command, 0, "", "")
        with mock.patch.object(svg, "_python_module", return_value=False), \
                mock.patch.object(svg.subprocess, "run", side_effect=run):
            for format in ("pdf", "png"):
                result, why = images.convert_svg(self.svg, self.cache, lambda name: "/tools/typst" if name == "typst" else None,
                                                 format=format, dpi=144, fonts=fonts)
                self.assertIsNotNone(result, why)
                self.assertEqual(result.suffix, "." + format)
        self.assertIn("144", seen[-1])

    def test_the_resvg_command_uses_options_resvg_has(self):
        # resvg 0.50's own options: -z/--zoom and --use-fonts-dir; an unknown one is read as the input file.
        from pdfmd_images import svg
        command = svg.converter_command("resvg", "in.svg", "out.png", "dir", "png", 192, "/fonts",
                                        lambda name: "/tools/" + name, "dir")
        self.assertEqual(command, ["/tools/resvg", "--zoom", "2", "--use-fonts-dir", "/fonts", "in.svg", "out.png"])
        self.assertEqual(svg.converter_command("resvg", "in.svg", "out.png", "dir", "png", 96, None,
                                               lambda name: "/tools/" + name, "dir"),
                         ["/tools/resvg", "--zoom", "1", "in.svg", "out.png"])

    def test_failed_typst_falls_through_to_resvg_and_keeps_the_png_suffix(self):
        from pdfmd_images import svg
        seen = []
        def run(command, **kwargs):
            seen.append(command)
            if command[0].endswith("typst"):
                return subprocess.CompletedProcess(command, 1, "", "cannot draw SVG")
            Path(command[-1]).write_bytes(PNG_BYTES)
            return subprocess.CompletedProcess(command, 0, "", "")
        with mock.patch.object(svg, "_python_module", return_value=False), \
                mock.patch.object(svg.subprocess, "run", side_effect=run):
            result, why = images.convert_svg(self.svg, self.cache, lambda name: "/tools/" + name if name in ("typst", "resvg") else None)
        self.assertIsNotNone(result, why)
        self.assertEqual(result.suffix, ".png")
        self.assertEqual(result.read_bytes(), PNG_BYTES)
        self.assertEqual([Path(call[0]).name for call in seen], ["typst", "resvg"])

    def test_each_converter_works_alone_for_pdf_and_png(self):
        from pdfmd_images import svg
        expected = ("rsvg-convert", "inkscape", "cairosvg", "svglib", "soffice", "typst", "resvg")
        self.assertEqual(svg.CONVERTERS, expected)
        def cairo(**kwargs):
            Path(kwargs["write_to"]).write_bytes(b"converted")
        def reportlab(drawing, filename, **kwargs):
            Path(filename).write_bytes(b"converted")
        modules = {"cairosvg": types.SimpleNamespace(svg2pdf=cairo, svg2png=cairo),
                   "svglib": types.ModuleType("svglib"), "svglib.svglib": types.SimpleNamespace(svg2rlg=lambda _: object()),
                   "reportlab": types.ModuleType("reportlab"),
                   "reportlab.graphics": types.SimpleNamespace(renderPDF=types.SimpleNamespace(drawToFile=reportlab),
                                                              renderPM=types.SimpleNamespace(drawToFile=reportlab))}
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            if "--convert-to" in command:
                out = Path(command[command.index("--outdir") + 1]) / (self.svg.stem + "." + command[command.index("--convert-to") + 1])
            elif "-o" in command:
                out = Path(command[command.index("-o") + 1])
            elif command[-1].startswith("--export-filename="):
                out = Path(command[-1].split("=", 1)[1])
            else:
                out = Path(command[-1])
            out.write_bytes(b"converted")
            return subprocess.CompletedProcess(command, 0, "", "")
        for name in expected:
            for format in ("pdf", "png"):
                with self.subTest(converter=name, format=format), mock.patch.dict(sys.modules, modules), \
                        mock.patch.object(svg, "_python_module", side_effect=lambda module: module == name or (name == "svglib" and module == "reportlab")), \
                        mock.patch.object(svg.subprocess, "run", side_effect=run):
                    result, why = images.convert_svg(self.svg, self.cache / name / format,
                        lambda tool: "/tools/" + tool if tool == name else None,
                        lambda: "/tools/soffice" if name == "soffice" else None, format=format)
                    self.assertIsNotNone(result, why)
                    self.assertEqual(result.suffix, ".png" if name == "resvg" else "." + format)
                    self.assertEqual(result.read_bytes(), b"converted")
        rsvg = [call for call in calls if call[0] == "/tools/rsvg-convert"]
        self.assertEqual(rsvg[0][1:3], ["-f", "pdf"])
        self.assertEqual(rsvg[-1][1:5], ["-z", "2", "-f", "png"])

    @unittest.skipUnless(shutil.which("typst"), "needs Typst")
    def test_real_typst_makes_an_image_sized_vector_pdf_and_png(self):
        import struct
        from pdfmd_images import svg
        fonts = self.directory / "fonts"
        fonts.mkdir()
        self.svg = self.svg.rename(self.directory / "a ü.svg")
        which = lambda name: shutil.which("typst") if name == "typst" else None
        with mock.patch.object(svg, "_python_module", return_value=False):
            pdf, why = images.convert_svg(self.svg, self.cache, which, fonts=fonts)
            self.assertIsNotNone(pdf, why)
            self.assertTrue(pdf.read_bytes().startswith(b"%PDF"))
            png, why = images.convert_svg(self.svg, self.cache, which, format="png", dpi=192, fonts=fonts)
            self.assertIsNotNone(png, why)
            self.assertEqual(struct.unpack(">II", png.read_bytes()[16:24]), (400, 200))
            try:
                from pypdf import PdfReader
            except ImportError:
                return
            page = PdfReader(pdf).pages[0]
            self.assertEqual((float(page.mediabox.width), float(page.mediabox.height)), (150, 75))
            self.assertEqual(len(page.images), 0)  # the SVG stayed vector


class ConcurrentCaching(unittest.TestCase):
    def run_writers(self, operation):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier = Barrier(2)
        replace = Path.replace

        def simultaneous(path, target):
            barrier.wait(timeout=10)
            return replace(path, target)

        with mock.patch.object(Path, "replace", simultaneous), ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(lambda _: operation(), range(2)))

    def test_remote_writers_do_not_share_a_partial_file(self):
        from pdfmd_images import remote
        class Response:
            headers = {"Content-Type": "image/png"}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return PNG_BYTES
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(remote, "_open", side_effect=lambda *a: Response()):
            results = self.run_writers(lambda: remote.fetch("https://example.test/image.png", Path(directory)))
            self.assertEqual(results[0], results[1])
            self.assertEqual(results[0][0].read_bytes(), PNG_BYTES)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_svg_writers_do_not_share_a_partial_file(self):
        from pdfmd_images import svg
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "a.svg"
            source.write_text(SVG, encoding="utf-8")
            def convert(name, svg_file, produced, *args, **kwargs):
                produced.write_bytes(b"%PDF-test")
                return True, ""
            with mock.patch.object(svg, "available_converters", return_value=["fake"]), mock.patch.object(svg, "_run", side_effect=convert):
                results = self.run_writers(lambda: svg.convert_svg(source, root / "cache"))
            self.assertEqual(results[0], results[1])
            self.assertEqual(results[0][0].read_bytes(), b"%PDF-test")
            self.assertEqual(len(list((root / "cache").iterdir())), 1)


class RefusedReplace(unittest.TestCase):
    """Windows refuses the rename over a cache entry that another writer is renaming onto or holds (PermissionError)."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pdfmd-images-refused-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.target = self.root / "entry.pdf"

    def refusing(self, times, other=None):
        """Path.replace that raises the Windows error ``times`` times (the other writer's file appearing first)."""
        replace, calls = Path.replace, []

        def refused(path, target):
            calls.append(path)
            if len(calls) <= times:
                if other is not None:
                    Path(target).write_bytes(other)
                raise PermissionError(13, "Access is denied", str(path), 5, str(target))
            return replace(path, target)
        return mock.patch.object(Path, "replace", refused), calls

    def test_the_other_writers_identical_file_is_success(self):
        import pdfmd_cache
        from pdfmd_images.cache import write_cached
        self.assertIs(write_cached, pdfmd_cache.write_cached)
        patched, calls = self.refusing(99, other=b"%PDF-same")
        with patched:
            write_cached(self.target, b"%PDF-same")
        self.assertEqual(len(calls), 1)
        self.assertEqual([item.name for item in self.root.iterdir()], ["entry.pdf"])

    def test_a_refusal_with_no_file_yet_is_tried_again(self):
        import pdfmd_cache
        patched, calls = self.refusing(2)
        with patched, mock.patch.object(pdfmd_cache, "REPLACE_PAUSE", 0):
            pdfmd_cache.write_cached(self.target, b"%PDF-mine")
        self.assertEqual(len(calls), 3)
        self.assertEqual(self.target.read_bytes(), b"%PDF-mine")
        self.assertEqual([item.name for item in self.root.iterdir()], ["entry.pdf"])

    def test_a_lasting_refusal_is_still_an_error_and_leaves_no_partial_file(self):
        import pdfmd_cache
        patched, calls = self.refusing(99, other=b"something else")
        with patched, mock.patch.object(pdfmd_cache, "REPLACE_PAUSE", 0), self.assertRaises(PermissionError):
            pdfmd_cache.write_cached(self.target, b"%PDF-mine")
        self.assertEqual(len(calls), pdfmd_cache.REPLACE_TRIES)
        self.assertEqual([item.name for item in self.root.iterdir()], ["entry.pdf"])

    def test_the_emoji_pictures_use_the_same_writer(self):
        import pdfmd_cache
        from pdfmd_unicode import colorfont
        self.assertIs(colorfont.write_cached, pdfmd_cache.write_cached)


class Arguments(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-images-args-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        (self.directory / "a.svg").write_text(SVG, encoding="utf-8")
        self.cache = self.directory / "cache"
        patcher = mock.patch.dict(os.environ, {**cache_env(self.cache)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def document(self, text):
        path = self.directory / "d.md"
        path.write_text(text, encoding="utf-8")
        return path

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_unreachable_svg_and_png_are_removed_before_the_writer(self):
        for suffix in ("svg", "png"):
            for down in (False, True):
                with self.subTest(suffix=suffix, down=down):
                    url = f"https://example.invalid/unreachable.{suffix}"
                    source = self.document(f"Before ![lost image]({url}) after.\n")
                    pdfmd.SVG_WARNED.clear()
                    errors = io.StringIO()
                    with mock.patch("pdfmd_images.fetch_remote", return_value=(None, "no DNS", down)), redirect_stderr(errors):
                        args = pdfmd.image_filter_args(None, [source])
                    self.assertEqual(errors.getvalue().count("WARN"), 1, errors.getvalue())
                    self.assertIn(url, errors.getvalue())
                    self.assertIn("--metadata-file", args)
                    done = subprocess.run([PANDOC, str(source), "-t", "latex", *args], capture_output=True, text=True)
                    self.assertEqual(done.returncode, 0, done.stderr)
                    self.assertNotIn("includegraphics", done.stdout)
                    self.assertNotIn("includesvg", done.stdout)
                    self.assertIn("lost image", done.stdout)

    @unittest.skipUnless(PANDOC and shutil.which("xelatex"), "needs Pandoc and XeLaTeX")
    def test_unreachable_images_build_with_the_first_engine(self):
        script = ("import sys; sys.path.insert(0, sys.argv.pop(1)); import pdfmd, pdfmd_images; "
                  "pdfmd_images.fetch_remote = lambda *a, **k: (None, 'no DNS', True); pdfmd.main()")
        for suffix in ("svg", "png"):
            with self.subTest(suffix=suffix):
                url = f"https://example.invalid/badge.{suffix}"
                source = self.document(f"---\ntitle: Offline\n---\n\nBefore ![lost image]({url}) after.\n")
                done = subprocess.run([sys.executable, "-c", script, str(ROOT), str(source), "-e", "xelatex",
                                       "--no-stamp", "--no-backup"], capture_output=True, text=True,
                                      env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"})
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertTrue(source.with_suffix(".pdf").is_file())
                self.assertNotIn("xelatex failed", done.stderr)
                self.assertEqual(done.stderr.count(url), 1, done.stderr)

    def test_nothing_is_added_for_a_document_without_such_images(self):
        self.assertEqual(pdfmd.image_filter_args(None, [self.document("Just text ![p](photo.png)\n")]), [])

    def test_a_raw_includegraphics_gets_graphicx_even_for_a_raster(self):
        args = pdfmd.image_filter_args(None, [self.document("\\includegraphics{photo.png}\n")])
        self.assertEqual(args[0], "--include-in-header")
        self.assertTrue(args[1].endswith("graphicx.tex"))

    def test_no_converter_is_a_warning_naming_the_file_and_the_fix(self):
        source = self.document("\\includegraphics{a.svg}\n")
        pdfmd.SVG_WARNED.clear()
        errors = io.StringIO()
        with mock.patch.object(pdfmd, "which", return_value=None), mock.patch.object(pdfmd, "resolve_soffice", return_value=None), \
                mock.patch("pdfmd_images.svg._python_module", return_value=False), redirect_stderr(errors):
            args = pdfmd.image_filter_args(None, [source])
        self.assertIn("a.svg is an SVG and LaTeX cannot read it", errors.getvalue())
        self.assertIn("librsvg", errors.getvalue())
        self.assertNotIn("--lua-filter", args)

    def test_no_auto_svg_turns_it_off(self):
        self.assertEqual(pdfmd.image_filter_args(["svg"], [self.document("\\includegraphics{a.svg}\n")]), [])

    def test_pandocs_own_conversion_is_left_alone_for_a_markdown_image(self):
        source = self.document("![a](a.svg)\n")
        with mock.patch.object(pdfmd, "which", side_effect=lambda name: "/usr/bin/rsvg-convert" if name == "rsvg-convert" else None):
            self.assertEqual(pdfmd.image_filter_args(None, [source]), [])

    def test_resolution_layers_cli_and_worker_state(self):
        from pdfmd_filters import image_dpi_for
        source = self.document("---\npdfmd-options: {image-dpi: 144}\n---\n![a](a.svg)\n")
        metadata = self.directory / "metadata.yaml"
        metadata.write_text("pdfmd-options: {image-dpi: 120}\n")
        with mock.patch.object(pdfmd, "IMAGE_DPI_CLI", None), \
                mock.patch.object(pdfmd, "config_options", return_value={"image-dpi": 96}):
            self.assertEqual(image_dpi_for(source, [metadata]), 144)
            source.write_text("![a](a.svg)\n")
            self.assertEqual(image_dpi_for(source, [metadata]), 120)
            self.assertEqual(image_dpi_for(source), 96)
            with mock.patch.object(pdfmd, "IMAGE_DPI_CLI", 72):
                self.assertEqual(image_dpi_for(source, [metadata]), 72)
                self.assertEqual(pdfmd.worker_state()["IMAGE_DPI_CLI"], 72)
        with mock.patch.object(pdfmd, "IMAGE_DPI_CLI", None), \
                mock.patch.object(pdfmd, "config_options", return_value={}):
            self.assertEqual(image_dpi_for(source), 192)
            self.assertEqual(image_dpi_for(source, default=300), 300)

    def test_raster_fallback_cache_tracks_resolution(self):
        source = self.document("![a](a.svg)\n")
        from pdfmd_images import svg
        def draw(name, file, produced, *args, **kwargs):
            produced.write_bytes(PNG_BYTES)
            return True, ""
        with mock.patch.object(svg, "available_converters", return_value=["resvg"]), \
                mock.patch.object(svg, "_run", side_effect=draw) as run:
            first, _ = images.convert_svg(self.directory / "a.svg", self.cache, dpi=144)
            second, _ = images.convert_svg(self.directory / "a.svg", self.cache, dpi=288)
            self.assertNotEqual(first, second)
            self.assertEqual(images.convert_svg(self.directory / "a.svg", self.cache, dpi=144)[0], first)
            self.assertEqual(run.call_count, 2)
        self.assertEqual(pdfmd.image_filter_args(["svg"], [source], format="png"), [])


class Remote(unittest.TestCase):
    """fetch() against a local server."""

    def setUp(self):
        import http.server
        import threading
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-images-remote-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.hits = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                outer.hits.append(self.path)
                if self.path.startswith("/missing"):
                    self.send_response(404)
                    self.end_headers()
                    return
                kind, body = (("image/svg+xml", SVG.encode()) if self.path.startswith("/badge") else
                              ("text/html", b"<html></html>") if self.path.startswith("/page") else
                              ("image/png", PNG_BYTES))
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        import socketserver

        class Server(http.server.ThreadingHTTPServer):
            def server_bind(self):                      # HTTPServer.server_bind asks DNS for the host's name: slow
                socketserver.TCPServer.server_bind(self)
                self.server_name, self.server_port = "127.0.0.1", self.server_address[1]

        self.server = Server(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server.block_on_close = False
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.02), daemon=True).start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        if not getattr(self, "stopped", False):
            self.stopped = True
            self.server.shutdown()
            self.server.server_close()

    def test_a_fetched_image_is_kept_and_not_fetched_again(self):
        first, why, down = images.fetch_remote(f"{self.base}/pic", self.directory)
        self.assertEqual((why, down), ("", False))
        self.assertEqual(first.suffix, ".png")
        self.assertEqual(first.read_bytes(), PNG_BYTES)
        second, _, _ = images.fetch_remote(f"{self.base}/pic", self.directory)
        self.assertEqual(second, first)
        self.assertEqual(self.hits, ["/pic"])

    def test_an_old_copy_is_fetched_again_and_kept_if_that_fails(self):
        first, _, _ = images.fetch_remote(f"{self.base}/pic", self.directory, max_age_days=0)
        images.fetch_remote(f"{self.base}/pic", self.directory, max_age_days=0)
        self.assertEqual(self.hits, ["/pic", "/pic"])
        self.stop_server()
        again, why, _ = images.fetch_remote(f"{self.base}/pic", self.directory, max_age_days=0, timeout=2)
        self.assertEqual((again, why), (first, ""))                        # the copy it has is better than nothing

    def test_a_missing_file_a_page_and_a_dead_network_are_told_apart(self):
        none, why, down = images.fetch_remote(f"{self.base}/missing.png", self.directory)
        self.assertEqual((none, down), (None, False))
        self.assertIn("404", why)
        none, why, down = images.fetch_remote(f"{self.base}/page", self.directory)
        self.assertEqual((none, down), (None, False))
        self.assertIn("not an image", why)
        port = self.server.server_address[1]
        self.stop_server()
        none, why, down = images.fetch_remote(f"http://127.0.0.1:{port}/x.png", self.directory, timeout=2)
        self.assertEqual((none, down), (None, True))

    @unittest.skipIf(os.name == "nt", "the stand-in programs are sh scripts")
    def test_an_svg_badge_is_converted_for_latex(self):
        bin_dir = self.directory / "bin"
        bin_dir.mkdir()
        fake(bin_dir, "rsvg-convert", 'while [ $# -gt 0 ]; do [ "$1" = -o ] && out="$2"; shift; done; printf %%PDF-1.4 > "$out"')
        source = self.directory / "d.md"
        source.write_text(f"![badge]({self.base}/badge.svg) ![photo]({self.base}/pic)\n", encoding="utf-8")
        environment = {**cache_env(self.directory / "cache"), "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
        with mock.patch.dict(os.environ, environment), mock.patch("pdfmd_images.svg._python_module", return_value=False), \
                mock.patch.object(pdfmd, "which", side_effect=lambda name: str(bin_dir / name) if name == "rsvg-convert" else None):
            args = pdfmd.image_filter_args(None, [source])
        map_file = Path(args[args.index("--metadata-file") + 1]).read_text(encoding="utf-8")
        self.assertIn(f"{self.base}/badge.svg", map_file)
        self.assertIn(".pdf", map_file.split(f"{self.base}/badge.svg")[1].split(",")[0])      # the badge became a PDF
        self.assertIn(".png", map_file.split(f"{self.base}/pic")[1])                          # the photo is the file kept
        with mock.patch.dict(os.environ, environment):
            self.assertEqual(pdfmd.image_filter_args(["remoteimages"], [source]), [])

    def test_a_dead_network_is_one_warning_not_one_per_image(self):
        source = self.directory / "d.md"
        port = self.server.server_address[1]
        self.stop_server()
        source.write_text("".join(f"![i{n}](http://127.0.0.1:{port}/{n}.png)\n" for n in range(3)), encoding="utf-8")
        errors = io.StringIO()
        with mock.patch.dict(os.environ, {**cache_env(self.directory / "cache")}), redirect_stderr(errors), \
                mock.patch("pdfmd_images.remote.urllib.request.urlopen", side_effect=__import__("urllib.error").error.URLError("no DNS")):
            args = pdfmd.image_filter_args(None, [source])
        self.assertEqual(errors.getvalue().count("no network"), 1)
        self.assertIn("--metadata-file", args)


@unittest.skipUnless(PANDOC, "needs Pandoc")
class Filter(unittest.TestCase):
    def test_gfm_space_in_reference_destination_matches_encoded_map(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "map.yaml").write_text('pdfmd-image-map: {"plot%20one.svg": "/cache/plot.pdf"}\n')
            source = "![Ref][p]\n\n[p]: <plot one.svg>\n"
            done = subprocess.run([PANDOC, "-f", "gfm", "-t", "latex", "--lua-filter",
                                   str(ROOT / "lib" / "pdfmd_lua" / "images.lua"), "--metadata-file", str(root / "map.yaml")],
                                  input=source, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("/cache/plot.pdf", done.stdout)

    def test_the_map_is_applied_to_markdown_and_raw_latex(self):
        directory = Path(tempfile.mkdtemp(prefix="pdfmd-images-lua-"))
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / "map.yaml").write_text('pdfmd-image-map: {"a.svg": "/c/a-1.pdf", "b": "/c/b 2.pdf"}\n', encoding="utf-8")
        (directory / "d.md").write_text("![x](a.svg)\n\n\\includegraphics[width=2cm]{a.svg} \\includesvg[scale=2]{b} "
                                        "\\includegraphics{other.png}\n", encoding="utf-8")
        done = subprocess.run([PANDOC, "d.md", "-t", "latex", "--lua-filter", str(ROOT / "lib" / "pdfmd_lua" / "images.lua"),
                               "--metadata-file", "map.yaml"], cwd=directory, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("{/c/a-1.pdf}", done.stdout)
        self.assertIn("\\includegraphics[width=2cm]{/c/a-1.pdf}", done.stdout)
        self.assertIn("\\includegraphics[scale=2]{/c/b 2.pdf}", done.stdout)
        self.assertIn("{other.png}", done.stdout)


LATEX = shutil.which("lualatex") or shutil.which("xelatex") or shutil.which("pdflatex")


@unittest.skipUnless(PANDOC and LATEX and shutil.which("pdftotext"), "needs Pandoc, a LaTeX engine and pdftotext")
@unittest.skipUnless(shutil.which("rsvg-convert") or shutil.which("inkscape") or shutil.which("soffice"), "needs an SVG converter")
class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-images-e2e-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        (self.directory / "a.svg").write_text(SVG.replace("</svg>", '<text x="100" y="55" font-size="20">SVGWORD</text></svg>'),
                                              encoding="utf-8")
        (self.directory / "raw.md").write_text("---\ntitle: Raw\n---\n\n\\begin{figure}\n\\centering\n"
                                               "\\includegraphics[width=0.5\\textwidth]{a.svg}\n\\caption{raw svg}\n\\end{figure}\n",
                                               encoding="utf-8")
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.directory / "xdg"), "APPDATA": str(self.directory / "xdg"), **cache_env(self.directory / "cache"),
                    "PDFMD_CONFIG": ""}

    def build(self, name, *args):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), name, "-e", Path(LATEX).name, *args], cwd=self.directory,
                              capture_output=True, text=True, env=self.env)

    def test_a_raw_includegraphics_of_an_svg_builds(self):
        done = self.build("raw.md")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.directory / "raw.pdf").is_file())
        self.assertEqual(len(list((self.directory / "cache" / "pdfmd" / "images").glob("a-*.pdf"))), 1)

    def test_no_auto_svg_leaves_it_to_latex_which_cannot(self):
        done = self.build("raw.md", "--no-auto", "svg")
        self.assertEqual(done.returncode, 1)


if __name__ == "__main__":
    unittest.main()
