"""A parts build names the snapshots of its files in one BACKUP line (the per-file lines are for --verbose)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
ENGINES = [name for name in ("lualatex", "xelatex", "pdflatex") if shutil.which(name)]


def folders(*names: str) -> str:
    """The folders of a BACKUP line, with the separator of the platform (display_path shows paths the way the OS writes them)."""
    return ", ".join(name.replace("/", os.sep) for name in names)


class Summary(unittest.TestCase):
    def test_one_snapshot_is_named_as_before_and_several_make_one_line(self):
        when = datetime(2026, 10, 24, 17, 33, 19)
        one = [Path(".backups/report.md.bak.20261024173319")]
        self.assertEqual(pdfmd.backup_summary(Path("report.md"), one, when), "BACKUP  " + pdfmd.display_path(one[0]))
        many = [Path(".backups/report.md.bak.1"), *(Path(f"parts/.backups/{n}.md.bak.1") for n in ("10-a", "20-b", "30-c"))]
        self.assertEqual(pdfmd.backup_summary(Path("report.md"), many, when),
                         "BACKUP  report.md + 3 parts -> " + folders(".backups/", "parts/.backups/") + " (20261024-173319)")
        self.assertEqual(pdfmd.backup_summary(Path("report.md"), many[1:3], when),
                         "BACKUP  2 parts -> " + folders("parts/.backups/") + " (20261024-173319)")
        self.assertEqual(pdfmd.backup_summary(Path("report.md"), many[:2], when),
                         "BACKUP  report.md + 1 part -> " + folders(".backups/", "parts/.backups/") + " (20261024-173319)")


@unittest.skipUnless(PANDOC and ENGINES, "needs Pandoc and a LaTeX engine")
class Builds(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-backup-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        (self.directory / "parts").mkdir()
        (self.directory / "report.md").write_text("---\ntitle: Report\nauthor: A\npdfmd-options:\n  parts: auto\n---\n", encoding="utf-8")
        for name in ("10-introduction", "20-procedure", "30-results"):
            (self.directory / "parts" / f"{name}.md").write_text(f"# {name[3:]}\n\nText of {name}.\n", encoding="utf-8")

    def run_pdfmd(self, *args: str):
        environment = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args, "-e", ENGINES[0], "--no-cache"], cwd=self.directory,
                              capture_output=True, text=True, encoding="utf-8", env=environment)

    def test_a_parts_build_names_its_snapshots_in_one_line(self):
        (self.directory / "metadata.yaml").write_text("pdfmd-options:\n  backup: true\n", encoding="utf-8")
        done = self.run_pdfmd("report.md")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        lines = [line for line in done.stdout.splitlines() if line.startswith("BACKUP")]
        self.assertEqual(len(lines), 1, done.stdout)
        self.assertRegex(lines[0], r"^BACKUP  report\.md \+ 3 parts -> " + re.escape(folders(".backups/", "parts/.backups/")) + r" \(\d{8}-\d{6}\)$")
        self.assertEqual(len(list((self.directory / "parts" / ".backups").iterdir())), 3)         # the files are all there
        again = self.run_pdfmd("report.md")
        self.assertNotIn("BACKUP", again.stdout)                                               # nothing changed: nothing said
        verbose = self.run_pdfmd("report.md", "--verbose")
        self.assertNotIn("\nBACKUP  ", "\n" + verbose.stdout)
        (self.directory / "parts" / "20-procedure.md").write_text("# procedure\n\nChanged.\n", encoding="utf-8")
        edited = self.run_pdfmd("report.md", "--verbose")
        self.assertEqual(len([line for line in edited.stdout.splitlines() if line.startswith("BACKUP")]), 1, edited.stdout)


if __name__ == "__main__":
    unittest.main()
