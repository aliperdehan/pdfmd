"""Office hybrid attachments honour folder settings and command-line overrides."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd  # noqa: E402


class OfficeHybridSettings(unittest.TestCase):
    def test_folder_overrides_user_config_in_both_directions_and_cli_wins(self):
        for global_on, folder_on in ((False, True), (True, False)):
            with self.subTest(global_on=global_on), tempfile.TemporaryDirectory() as scratch:
                folder = Path(scratch)
                (folder / ".pdfmd").mkdir()
                (folder / ".pdfmd" / "config.yaml").write_text(
                    f"options: {{hybrid: {str(folder_on).lower()}}}\n", encoding="utf-8")
                path = folder / "input.docx"
                path.write_bytes(b"PK-office")
                with mock.patch.object(pdfmd, "HYBRID_CLI", None), mock.patch.object(
                        pdfmd, "load_config", return_value={"options": {"hybrid": global_on}}):
                    self.assertEqual(pdfmd.resolve_hybrid(path, []), folder_on)
                    for cli in (False, True):
                        with mock.patch.object(pdfmd, "HYBRID_CLI", cli):
                            self.assertEqual(pdfmd.resolve_hybrid(path, []), cli)


@unittest.skipIf(os.name == "nt", "the stand-in uses a POSIX launcher")
@unittest.skipUnless(shutil.which("pandoc") and pdfmd.pypdf is not None, "needs Pandoc and pypdf")
class OfficeHybridFolder(unittest.TestCase):
    def test_folder_enable_disable_and_command_line_overrides(self):
        for outer_on, folder_on, cli, expected in ((False, True, (), True), (True, False, (), False),
                                                  (True, False, ("--hybrid",), True),
                                                  (False, True, ("--no-hybrid",), False)):
            with self.subTest(outer_on=outer_on, folder_on=folder_on, cli=cli), tempfile.TemporaryDirectory() as scratch:
                folder = Path(scratch)
                project = folder / "project"
                project.mkdir()
                (project / ".pdfmd").mkdir()
                (project / ".pdfmd" / "config.yaml").write_text(
                    f"options: {{hybrid: {str(folder_on).lower()}}}\n", encoding="utf-8")
                outer = folder / ".pdfmd"
                outer.mkdir()
                (outer / "config.yaml").write_text(
                    f"options: {{hybrid: {str(outer_on).lower()}}}\n", encoding="utf-8")
                document = project / "input.odt"
                document.write_bytes(b"PK-editable-office-document")
                blank = folder / "blank.pdf"
                writer = pdfmd.pypdf.PdfWriter()
                writer.add_blank_page(200, 200)
                with blank.open("wb") as handle:
                    writer.write(handle)
                binary = folder / "bin"
                binary.mkdir()
                tool = binary / "soffice"
                tool.write_text(f"#!{sys.executable}\n" +
                                "import os, sys, shutil\nfrom pathlib import Path\n"
                                "if '--version' in sys.argv:\n print('LibreOffice 24.2'); sys.exit()\n"
                                "out = Path(sys.argv[sys.argv.index('--outdir') + 1])\n"
                                "out.mkdir(parents=True, exist_ok=True)\n"
                                "shutil.copyfile(os.environ['PDFMD_FIXTURE_PDF'], out / (Path(sys.argv[-1]).stem + '.pdf'))\n",
                                encoding="utf-8")
                tool.chmod(0o755)
                env = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ.get("PATH", ""),
                       "PDFMD_FIXTURE_PDF": str(blank), "XDG_CONFIG_HOME": str(folder / "config"),
                       "XDG_CACHE_HOME": str(folder / "cache"), "XDG_DATA_HOME": str(folder / "data"),
                       "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
                done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), str(document),
                                       "-e", "soffice", "-o", "out.pdf", "--no-stamp", "--no-backup", *cli],
                                      cwd=project, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                attachments = pdfmd.pypdf.PdfReader(project / "out.pdf").attachments
                self.assertEqual("Original.odt" in attachments, expected, done.stdout + done.stderr)
                if expected:
                    self.assertEqual(attachments["Original.odt"][0], document.read_bytes())
