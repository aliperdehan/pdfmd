"""A PDF given to pdfmd is read, not built (v3.22.7): direction from the files, a pdfmd
source restored, everything else handed to batchocr with the flags pdfmd does not know.
batchocr is a stand-in script that records how it was called."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import pypdf
except ImportError:                                  # pragma: no cover
    pypdf = None

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# never read or write the real user's config and state while testing
import os as _os, tempfile as _tempfile  # noqa: E402
_os.environ["PDFMD_CONFIG"] = ""
_os.environ["XDG_CONFIG_HOME"] = _tempfile.mkdtemp(prefix="pdfmd-test-config-")

import pdfmd  # noqa: E402

FAKE = '''
import json, sys
if "--version" in sys.argv:
    print("batchocr %s")
    raise SystemExit(0)
open(%r, "w").write(json.dumps(sys.argv[1:]))
raise SystemExit(%d)
'''


class PdfInput(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.addCleanup(self.folder.cleanup)
        (self.root / "a.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
        self.record = self.root / "call.json"

    def fake(self, version="1.2.4", code=0) -> str:
        script = self.root / "fake_batchocr.py"
        script.write_text(FAKE % (version, str(self.record), code), encoding="utf-8")
        return f"{sys.executable} {script}"

    def run_pdfmd(self, *args: str, batchocr: str | None = None, check=False):
        env = dict(os.environ)
        env.pop("PDFMD_BATCHOCR", None)
        if batchocr:
            env["PDFMD_BATCHOCR"] = batchocr
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=self.root, env=env,
                              capture_output=True, text=True)

    def call(self) -> list[str]:
        return json.loads(self.record.read_text(encoding="utf-8"))

    def test_a_pdf_is_read_as_markdown_by_default(self):
        done = self.run_pdfmd("a.pdf", batchocr=self.fake())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.call(), ["a.pdf", "--to", "md"])

    def test_unknown_flags_go_to_batchocr_unchanged_and_abbreviations_do_not_swallow_them(self):
        self.run_pdfmd("a.pdf", "--output", "out/b.md", "--ocr", "off", "--lang", "eng", "-c", "--page-breaks",
                       "-q", "--no-color", "--keep-headers", batchocr=self.fake())
        call = self.call()
        self.assertEqual(call[:5], ["a.pdf", "--to", "md", "-o", "out/b.md"])
        for flag in ("--ocr", "off", "--lang", "eng", "-c", "--page-breaks", "-q", "--no-color", "--keep-headers"):
            self.assertIn(flag, call)

    def test_verbosity_is_counted_for_batchocr(self):
        self.run_pdfmd("a.pdf", "-vv", batchocr=self.fake())
        self.assertEqual(self.call().count("-v"), 2)

    def test_direction_from_the_output_and_to(self):
        self.run_pdfmd("a.pdf", "-o", "t.txt", batchocr=self.fake())
        self.assertEqual(self.call()[1:3], ["--to", "txt"])
        self.run_pdfmd("a.pdf", "-t", "gfm", batchocr=self.fake())
        self.assertEqual(self.call()[1:3], ["--to", "md"])

    def test_an_output_folder_gets_the_name_of_the_pdf(self):
        self.run_pdfmd("a.pdf", "-o", "notes", batchocr=self.fake())
        self.assertEqual(self.call()[3:], ["-o", "notes/a.md"])

    def test_contradictions_are_refused_before_anything_runs(self):
        for args in (["a.pdf", "-o", "a.pdf"], ["a.pdf", "--to", "html"], ["a.pdf", "-o", "x.txt", "--to", "md"],
                     ["a.pdf", "-o", "x.docx"], ["a.pdf", "--to", "pdf"]):
            done = self.run_pdfmd(*args, batchocr=self.fake())
            self.assertEqual(done.returncode, 1, args)
            self.assertFalse(self.record.exists(), args)

    def test_pdf_and_markdown_together_are_refused(self):
        (self.root / "b.md").write_text("x\n", encoding="utf-8")
        done = self.run_pdfmd("a.pdf", "b.md", batchocr=self.fake())
        self.assertEqual(done.returncode, 1)
        self.assertIn("cannot be given together", done.stderr)

    def test_the_exit_status_is_batchocrs(self):
        self.assertEqual(self.run_pdfmd("a.pdf", batchocr=self.fake(code=1)).returncode, 1)

    def test_missing_or_old_batchocr_says_how_to_install(self):
        old = self.run_pdfmd("a.pdf", batchocr=self.fake(version="1.0.0"))
        self.assertEqual(old.returncode, 1)
        self.assertIn("too old", old.stderr)
        self.assertIn("pdfmd --install batchocr", old.stderr)
        self.assertFalse(self.record.exists())

    @unittest.skipIf(pypdf is None, "pypdf not installed")
    def test_a_pdf_with_its_source_is_restored_not_read(self):
        (self.root / "r.md").write_text("---\ntitle: T\n---\n\nHello.\n", encoding="utf-8")
        pdf = self.root / "r.pdf"
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with pdf.open("wb") as handle:
            writer.write(handle)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            pdfmd.attach_source_after_success(self.root / "r.md", pdf, [], [], [], None, False)
        fake = self.fake()
        done = self.run_pdfmd("r.pdf", batchocr=fake)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.root / "r.restored" / "r.md").is_file())
        self.assertFalse(self.record.exists())
        self.run_pdfmd("r.pdf", "--extract", "-o", "r.out.md", batchocr=fake)
        self.assertEqual(self.call()[:3], ["r.pdf", "--to", "md"])


class Install(unittest.TestCase):
    def test_batchocr_is_an_install_kind_and_the_spec_can_be_overridden(self):
        self.assertIn("batchocr", pdfmd.INSTALL_KINDS)
        self.assertIn(pdfmd.BATCHOCR_TAG, pdfmd.batchocr_spec())
        self.assertIn("[md]", pdfmd.batchocr_spec())


if __name__ == "__main__":
    unittest.main()
