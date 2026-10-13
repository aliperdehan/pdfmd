"""v3.29.6: `pan-tec`, the first version of pdfmd (a shell function around Pandoc and Tectonic) as a command."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


class Translate(unittest.TestCase):
    def test_tectonic_and_quiet_output_are_added(self):
        self.assertEqual(pdfmd.pan_tec_translate(["test.md", "-o", "ex.pdf"]),
                         ["-e", "tectonic", "test.md", "-o", "ex.pdf", "--pdf-engine-opt=--chatter=minimal"])

    def test_an_engine_of_your_own_is_kept(self):
        for engine in (["-e", "typst"], ["-etypst"], ["--engine=typst"], ["--pdf-engine=typst"]):
            out = pdfmd.pan_tec_translate(["a.md", *engine])
            self.assertNotIn("tectonic", out)

    def test_a_chatter_level_of_your_own_is_kept(self):
        out = pdfmd.pan_tec_translate(["a.md", "--pdf-engine-opt=--chatter=default"])
        self.assertEqual(out.count("--pdf-engine-opt=--chatter=default"), 1)
        self.assertNotIn("--pdf-engine-opt=--chatter=minimal", out)

    def test_it_is_a_command(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('pan-tec = "pdfmd:pan_tec_main"', text)


if __name__ == "__main__":
    unittest.main()
