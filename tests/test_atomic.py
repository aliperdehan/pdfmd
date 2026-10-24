"""Writing a file in place goes through a temporary file and os.replace(): a write that stops half-way leaves the old file whole."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

try:
    import pypdf
except ImportError:  # pragma: no cover
    pypdf = None


class Helper(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-atomic-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.file = self.directory / "doc.md"
        self.file.write_text("old\n", encoding="utf-8")

    def only_the_file(self):
        self.assertEqual([path.name for path in self.directory.iterdir()], ["doc.md"])      # no temporary file left behind

    def test_it_writes_text_and_bytes(self):
        pdfmd.atomic_write_text(self.file, "new é\n")
        self.assertEqual(self.file.read_text(encoding="utf-8"), "new é\n")
        pdfmd.atomic_write_bytes(self.file, b"\x00\x01")
        self.assertEqual(self.file.read_bytes(), b"\x00\x01")
        fresh = self.directory / "fresh.txt"
        pdfmd.atomic_write_text(fresh, "made\n")
        self.assertEqual(fresh.read_text(encoding="utf-8"), "made\n")

    def test_write_text_lf_keeps_the_line_ends_it_is_given(self):
        pdfmd.write_text_lf(self.file, "a\nb\n")
        self.assertEqual(self.file.read_bytes(), b"a\nb\n")

    def test_a_failure_while_writing_leaves_the_old_file_whole(self):
        for name, patched in (("the flush to disk", mock.patch("os.fsync", side_effect=OSError(28, "No space left on device"))),
                              ("the rename", mock.patch("os.replace", side_effect=OSError("denied")))):
            with self.subTest(name=name), patched, self.assertRaises(OSError):
                pdfmd.atomic_write_text(self.file, "half of the new text\n")
            self.assertEqual(self.file.read_text(encoding="utf-8"), "old\n")
            self.only_the_file()

    def test_text_that_cannot_be_encoded_leaves_the_old_file_whole(self):
        with self.assertRaises(UnicodeEncodeError):
            pdfmd.atomic_write_text(self.file, "ok ☃", encoding="ascii")
        self.assertEqual(self.file.read_text(encoding="utf-8"), "old\n")
        self.only_the_file()

    def test_an_interrupt_leaves_the_old_file_whole(self):
        with mock.patch("os.fsync", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            pdfmd.atomic_write_bytes(self.file, b"x" * 100000)
        self.assertEqual(self.file.read_text(encoding="utf-8"), "old\n")
        self.only_the_file()

    def test_a_process_that_dies_before_the_rename_leaves_the_old_file_whole(self):
        script = textwrap.dedent(f"""
            import os, sys
            sys.path.insert(0, {str(ROOT)!r})
            os.environ["PDFMD_CONFIG"] = ""
            import pdfmd
            os.replace = lambda *arguments: os._exit(9)          # the machine goes away at the rename
            pdfmd.atomic_write_text(__import__("pathlib").Path({str(self.file)!r}), "new\\n" * 50000)
        """)
        done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(done.returncode, 9, done.stderr)
        self.assertEqual(self.file.read_text(encoding="utf-8"), "old\n")

    @unittest.skipIf(sys.platform == "win32", "modes and symlinks")
    def test_the_mode_is_kept_and_a_symlink_is_written_through(self):
        os.chmod(self.file, 0o640)
        pdfmd.atomic_write_text(self.file, "new\n")
        self.assertEqual(stat.S_IMODE(self.file.stat().st_mode), 0o640)
        link = self.directory / "link.md"
        link.symlink_to(self.file.name)
        pdfmd.atomic_write_text(link, "via the link\n")
        self.assertTrue(link.is_symlink())
        self.assertEqual(self.file.read_text(encoding="utf-8"), "via the link\n")


class Writers(unittest.TestCase):
    """The writers named in the review go through it: a failure at the rename changes nothing."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-atomic-"))
        self.addCleanup(shutil.rmtree, self.directory, True)

    def test_the_build_notes_stamp(self):
        document = self.directory / "d.md"
        document.write_text("---\ntitle: T\n---\n\nText\n", encoding="utf-8")
        before = document.read_bytes()
        with mock.patch("os.replace", side_effect=OSError("denied")), self.assertRaises(OSError):
            pdfmd.apply_stamp(document, "Compiled with a pdfmd -- 2026-01-01 00:00:00", "replace", False)
        self.assertEqual(document.read_bytes(), before)
        pdfmd.apply_stamp(document, "Compiled with a pdfmd -- 2026-01-01 00:00:00", "replace", False)
        self.assertIn("BUILD NOTES", document.read_text(encoding="utf-8"))
        self.assertEqual([path.name for path in self.directory.iterdir()], ["d.md"])

    @unittest.skipIf(pypdf is None, "needs pypdf")
    def test_a_pdf_a_finishing_step_rewrites(self):
        import pdfmd_inkmd
        pdf = self.directory / "d.pdf"
        pdf.write_bytes(pdfmd_inkmd.compile("# Hi\n\nText\n"))
        before = pdf.read_bytes()
        with mock.patch("os.replace", side_effect=OSError("denied")), self.assertRaises(OSError):
            pdfmd.write_pdf_attachments(pdf, {"a.txt": b"attached"})
        self.assertEqual(pdf.read_bytes(), before)
        self.assertEqual([path.name for path in self.directory.iterdir()], ["d.pdf"])
        pdfmd.write_pdf_attachments(pdf, {"a.txt": b"attached"})
        self.assertEqual(pdfmd.read_pdf_attachments(pdf)["a.txt"], b"attached")

    def config_environment(self, text: str):
        config = self.directory / "config.yaml"
        config.write_text(text, encoding="utf-8")
        patched = mock.patch.dict(os.environ, {"PDFMD_CONFIG": str(config), "PDFMD_NO_PROMPT": "1"})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(pdfmd.load_config.cache_clear)
        pdfmd.load_config.cache_clear()
        return config

    def test_the_config_file_of_init_backups(self):
        import argparse
        config = self.config_environment("options:\n  fallback: char\n")
        before = config.read_bytes()
        arguments = argparse.Namespace(backup_folder=None, global_=True)
        with mock.patch("os.replace", side_effect=OSError("denied")), self.assertRaises(OSError):
            pdfmd.init_backups_command(arguments)
        self.assertEqual(config.read_bytes(), before)
        pdfmd.load_config.cache_clear()                    # (the failed run had put its keys into the cached dict)
        self.assertEqual(pdfmd.init_backups_command(arguments), 0)
        self.assertIn("backup:", config.read_text(encoding="utf-8"))
        self.assertIn("fallback: char", config.read_text(encoding="utf-8"))

    def test_the_config_and_metadata_files_of_the_setup(self):
        import pdfmd_setup
        config = self.config_environment("options:\n  fallback: char\n")
        metadata = config.with_name("metadata.yaml")
        metadata.write_text("toc: true\n", encoding="utf-8")
        before = (config.read_bytes(), metadata.read_bytes())

        def run(stores, *arguments, **keywords):
            stores["config"].setdefault("options", {})["missing"] = "ask"
            stores["metadata"]["toc"] = False
            return True

        with mock.patch.object(pdfmd_setup, "run", run), mock.patch("os.replace", side_effect=OSError("denied")):
            pdfmd.setup_command("plain")
        self.assertEqual((config.read_bytes(), metadata.read_bytes()), before)         # the setup said it could not write
        self.assertEqual(sorted(path.name for path in self.directory.iterdir()), ["config.yaml", "metadata.yaml"])
        with mock.patch.object(pdfmd_setup, "run", run):
            pdfmd.setup_command("plain")
        self.assertIn("missing: ask", config.read_text(encoding="utf-8"))
        self.assertIn("toc: false", metadata.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
