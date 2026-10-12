"""v3.28.25: KaTeX's formulas in a WeasyPrint PDF are sized to the body font's x-height (x-height / 0.442 em)."""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


def sfnt(units: int, height: int, version: int = 4) -> bytes:
    head = bytearray(54)
    struct.pack_into(">H", head, 18, units)
    os2 = bytearray(96)
    struct.pack_into(">H", os2, 0, version)
    struct.pack_into(">h", os2, 86, height)
    directory = struct.pack(">IHHHH", 0x00010000, 2, 32, 1, 0)
    offset = 12 + 16 * 2
    entries = b""
    body = b""
    for tag, table in ((b"OS/2", os2), (b"head", head)):
        entries += tag + struct.pack(">III", 0, offset + len(body), len(table))
        body += bytes(table)
    return directory + entries + body


class XHeight(unittest.TestCase):
    def test_the_x_height_is_read_from_the_os2_table(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "f.ttf"
            path.write_bytes(sfnt(1000, 470))
            self.assertAlmostEqual(pdfmd.sfnt_x_height(path), 0.47)
            path.write_bytes(sfnt(2048, 1024))
            self.assertAlmostEqual(pdfmd.sfnt_x_height(path), 0.5)
            path.write_bytes(sfnt(1000, 470, version=1))             # an old OS/2 has no sxHeight
            self.assertIsNone(pdfmd.sfnt_x_height(path))
            path.write_bytes(b"not a font")
            self.assertIsNone(pdfmd.sfnt_x_height(path))
            self.assertIsNone(pdfmd.sfnt_x_height(Path(folder) / "missing.ttf"))

    def test_the_size_is_the_x_height_over_katexs(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "f.ttf"
            path.write_bytes(sfnt(1000, 473))
            pdfmd.katex_scale.cache_clear()
            fake = subprocess.CompletedProcess([], 0, stdout=f"Fake Serif\n{path}\n0", stderr="")
            with unittest.mock.patch.object(pdfmd.subprocess, "run", return_value=fake), \
                    unittest.mock.patch.object(pdfmd, "which", return_value="/usr/bin/fc-match"):
                self.assertEqual(pdfmd.katex_scale("Fake Serif"), 1.07)
                path.write_bytes(sfnt(1000, 900))                        # huge: kept within 1.4
                pdfmd.katex_scale.cache_clear()
                self.assertEqual(pdfmd.katex_scale("Fake Serif"), 1.4)
                pdfmd.katex_scale.cache_clear()
                other = subprocess.CompletedProcess([], 0, stdout=f"Another Font\n{path}\n0", stderr="")
                with unittest.mock.patch.object(pdfmd.subprocess, "run", return_value=other):
                    self.assertIsNone(pdfmd.katex_scale("Fake Serif"))   # fontconfig named another font: not installed
            pdfmd.katex_scale.cache_clear()


@unittest.skipUnless(shutil.which("pandoc") and shutil.which("weasyprint") and pdfmd.katex_runtime() is not None
                     and "stix two text" in (pdfmd.installed_font_families() or ()),
                     "needs Pandoc, WeasyPrint, KaTeX and STIX Two Text")
class Build(unittest.TestCase):
    def test_a_weasyprint_build_passes_the_size(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "d.md").write_text("---\ntitle: T\n---\n\n$x^2$\n", encoding="utf-8")
            env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "-e", "weasyprint", "--verbose"],
                                  cwd=root, env=env, capture_output=True, text=True, timeout=300)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("pdfmd-katex-scale=1.07", done.stdout + done.stderr)

    def test_a_weasyprint_report_builds_and_passes_the_size_of_a_named_font(self):
        # v3.28.25 read a variable the report route had not set (an UnboundLocalError, found by the full suite)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "a.md").write_text("---\ntitle: T\nmainfont: STIX Two Text\n---\n\n# One\n\n$x^2$\n", encoding="utf-8")
            (root / "b.md").write_text("# Two\n\nText.\n", encoding="utf-8")
            env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
            done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "-r", ".", "-e", "weasyprint", "-o", "r.pdf",
                                   "--verbose"], cwd=root, env=env, capture_output=True, text=True, timeout=300)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("pdfmd-katex-scale=1.07", done.stdout + done.stderr)


if __name__ == "__main__":
    import unittest.mock  # noqa: F401
    unittest.main()
