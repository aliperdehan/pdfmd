"""SVG for LaTeX engines (pdfmd_images, pdfmd_lua/images.lua) and the graphicx a raw \\includegraphics needs."""

from __future__ import annotations

import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
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

    def test_nothing_installed_says_what_to_install(self):
        with mock.patch("pdfmd_images.svg._python_module", return_value=False):
            pdf, why = images.convert_svg(self.svg, self.cache, self.which)
        self.assertIsNone(pdf)
        self.assertIn("rsvg", why)


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
            def convert(name, svg_file, produced, *args):
                produced.write_bytes(b"%PDF-test")
                return True, ""
            with mock.patch.object(svg, "available_converters", return_value=["fake"]), mock.patch.object(svg, "_run", side_effect=convert):
                results = self.run_writers(lambda: svg.convert_svg(source, root / "cache"))
            self.assertEqual(results[0], results[1])
            self.assertEqual(results[0][0].read_bytes(), b"%PDF-test")
            self.assertEqual(len(list((root / "cache").iterdir())), 1)


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
        self.assertEqual(args, [])


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
