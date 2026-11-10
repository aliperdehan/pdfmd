"""v3.31.36: kits, C4 (entry 3du, point 17): an attached source holds the options of the folder settings the build used and
`--restore` writes them to `.pdfmd/config.yaml` of the restored folder (the folder's own file, when there is one, wins)."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

try:
    import pypdf
    import yaml
except ImportError:                                      # pragma: no cover
    pypdf = yaml = None


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@unittest.skipIf(pypdf is None, "needs pypdf and PyYAML")
class Layers(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.folder = self.root / "course" / "LR1"
        self.md = write(self.folder / "report.md", "---\ntitle: T\n---\nText.\n")
        self.pdf = self.root / "LR1.pdf"
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with self.pdf.open("wb") as handle:
            writer.write(handle)
        pdfmd.load_config.cache_clear()
        pdfmd.ACTIVE_KITS.clear()
        self.addCleanup(pdfmd.load_config.cache_clear)

    def attach(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return pdfmd.source_attachments(self.md, self.pdf, [], [], [], None)

    def restore(self, attachments, out="back"):
        out_dir = self.root / out
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            status = pdfmd.restore_attachments_in_place(self.pdf, attachments, out_dir, False)
        return status, out_dir, printed.getvalue()

    def test_no_folder_settings_no_layers_and_format_2(self):
        _, _, manifest = self.attach()
        self.assertNotIn("layers", manifest)
        self.assertEqual(manifest["format"], 2)

    def test_the_layers_are_flattened_nearest_first_and_the_kit_is_left_out(self):
        write(self.root / "course" / ".pdfmd" / "config.yaml",
              "options:\n  bundle-max-mb: 7\n  strip-comments: false\n  kit: none\n  kit-stack: all\n")
        write(self.root / "course" / "LR1" / ".pdfmd" / "config.yaml", "options:\n  bundle-max-mb: 9\n  attach-source: true\n")
        _, _, manifest = self.attach()
        self.assertEqual(manifest["layers"], {"options": {"bundle-max-mb": 9, "strip-comments": False, "attach-source": True}})
        self.assertEqual(manifest["format"], 3)

    def test_a_restore_writes_the_settings_back(self):
        write(self.root / "course" / ".pdfmd" / "config.yaml", "options:\n  bundle-max-mb: 7\n")
        attachments, _, manifest = self.attach()
        status, out, printed = self.restore(attachments)
        self.assertEqual(status, 0)
        written = yaml.safe_load((out / ".pdfmd" / "config.yaml").read_text(encoding="utf-8"))
        self.assertEqual(written, {"options": {"bundle-max-mb": 7}})
        lines = pdfmd.requirement_lines(json.loads(attachments[pdfmd.ATTACH_MANIFEST]))
        self.assertTrue(any(line.startswith("FOLDER    settings the build used: bundle-max-mb") for line in lines), lines)

    def test_the_folders_own_file_wins_and_the_difference_is_said(self):
        write(self.root / "course" / ".pdfmd" / "config.yaml", "options:\n  bundle-max-mb: 7\n  strip-comments: false\n")
        attachments, _, _ = self.attach()
        write(self.root / "back" / ".pdfmd" / "config.yaml", "# mine\noptions:\n  bundle-max-mb: 3\n")
        status, out, printed = self.restore(attachments)
        self.assertEqual(status, 0)
        self.assertEqual((out / ".pdfmd" / "config.yaml").read_text(encoding="utf-8"), "# mine\noptions:\n  bundle-max-mb: 3\n")
        self.assertIn("is already in", printed)
        self.assertIn("bundle-max-mb: 7", printed)
        self.assertIn("strip-comments: False", printed)


if __name__ == "__main__":
    unittest.main()
