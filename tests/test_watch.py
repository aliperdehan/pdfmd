"""Watch snapshots notice input changes without reacting to build outputs."""
import os
import shutil
import subprocess
import sys
import time
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: F401
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pdfmd
from pdfmd_watch import watch_signature


class WatchSignature(unittest.TestCase):
    def test_deleting_older_metadata_changes_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "metadata.yaml"
            metadata.write_text("title: Test")
            source = root / "report.md"
            source.write_text("Source")
            os.utime(metadata, (1, 1))
            before = watch_signature(source)
            metadata.unlink()
            self.assertNotEqual(watch_signature(source), before)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_watch_rebuilds_after_metadata_deletion_and_ignores_output_changes(self):
        # cleaned up leniently: on Windows, terminate() ends pdfmd but not a Pandoc child still running in the folder, which
        # keeps it busy for a moment (CI, windows-latex)
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        root = Path(directory)
        (root / "report.md").write_text("Watch body.\n")
        metadata = root / "metadata.yaml"
        metadata.write_text("title: Test\n")
        os.utime(metadata, (1, 1))
        output = root / "result.html"
        env = {**os.environ, "TMPDIR": directory, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
               "XDG_CONFIG_HOME": str(root / "config"), "XDG_CACHE_HOME": str(root / "cache"),
               "XDG_DATA_HOME": str(root / "data")}
        process = subprocess.Popen([sys.executable, str(Path(pdfmd.__file__).parent / "scripts/pdfmd"),
                                    "--watch", "report.md", "--to", "html", "-o", "result.html",
                                    "--no-stamp", "--no-backup"], cwd=root, env=env,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 15
            while not output.exists() and time.monotonic() < deadline:
                time.sleep(0.1)
            self.assertTrue(output.exists())
            time.sleep(2)
            output.write_text("external output change")
            time.sleep(2)
            self.assertEqual(output.read_text(), "external output change")
            metadata.unlink()
            deadline = time.monotonic() + 15
            while output.read_text() == "external output change" and time.monotonic() < deadline:
                time.sleep(0.1)
            self.assertIn("Watch body", output.read_text())
        finally:
            process.terminate()
            process.wait(timeout=10)

    def test_add_change_and_delete_inputs_but_ignore_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "report.md"
            source.write_text("Source")
            output = root / "report.pdf"
            output.write_text("Output")
            baseline = watch_signature(source, {output})
            output.write_text("Changed output")
            self.assertEqual(watch_signature(source, {output}), baseline)
            metadata = root / "metadata.yaml"
            metadata.write_text("title: First")
            added = watch_signature(source, {output})
            self.assertNotEqual(added, baseline)
            metadata.write_text("title: Longer title")
            self.assertNotEqual(watch_signature(source, {output}), added)
            metadata.unlink()
            self.assertEqual(watch_signature(source, {output}), baseline)
            parts = root / "parts"
            parts.mkdir()
            part = parts / "one.md"
            part.write_text("Part")
            self.assertNotEqual(watch_signature(source, {output}), baseline)
            part.unlink()
            self.assertEqual(watch_signature(source, {output}), baseline)
