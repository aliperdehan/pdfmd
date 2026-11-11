"""An unsuccessful upward scaffold probe cannot stop another document's build."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class ScaffoldProbe(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="pdfmd-scaffold-probe-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.project = self.root / "course" / "project"
        self.project.mkdir(parents=True)
        self.write(self.project / "paper.md", "---\ntitle: Paper\n---\n\nDocument body.\n")
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.root / "config"),
                    "XDG_CACHE_HOME": str(self.root / "cache"), "XDG_DATA_HOME": str(self.root / "data"),
                    "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1"}

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def build(self, source="paper.md", *args):
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), source,
                               "--to", "html", "-s", "-o", "out.html", "--no-backup", "--no-stamp",
                               "--no-auto", "crossref", *args], cwd=self.project, env=self.env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done, (self.project / "out.html").read_text(encoding="utf-8")

    def test_stray_candidate_failures_are_verbose_notes_only(self):
        candidate = self.root / "brief.md"
        for content, reason in (
            ("---\npdfmd-options: {kit: missing-kit}\n---\n", "missing-kit"),
            ("---\npdfmd-options: {parts: absent}\n---\n", "not a folder"),
            ("---\npdfmd-options: {parts: auto}\n---\n", "parts folder"),
            ("---\npdfmd-options: [broken\n---\n", "expected"),
        ):
            with self.subTest(reason=reason):
                self.write(candidate, content)
                done, html = self.build("paper.md", "--verbose")
                self.assertIn("Document body.", html)
                notes = [line for line in done.stdout.splitlines() if "skipped scaffold candidate" in line]
                self.assertTrue(any("brief.md" in line and reason in line for line in notes), done.stdout)
                self.assertNotIn("WARN", done.stdout + done.stderr)
                quiet, _ = self.build()
                self.assertNotIn("brief.md", quiet.stdout + quiet.stderr)

    def test_unreadable_candidate_is_skipped(self):
        # Invalid UTF-8 exercises a real read failure even for privileged test users.
        (self.root / "brief.md").write_bytes(b"\xff")
        done, html = self.build("paper.md", "--verbose")
        self.assertIn("Document body.", html)
        self.assertIn("skipped scaffold candidate", done.stdout)
        self.assertIn("brief.md", done.stdout)
        self.assertIn("decode", done.stdout)
        self.assertNotIn("WARN", done.stdout + done.stderr)

    def test_command_line_kit_only_found_above_source_does_not_stop_build(self):
        self.write(self.root / "brief.md", "Unrelated document.\n")
        self.write(self.project / "kits" / "house" / ".kit",
                   "kit-format: 1\nname: house\nversion: 1\n")
        done, html = self.build("paper.md", "--kit", "house", "--verbose")
        self.assertIn("Document body.", html)
        self.assertTrue(any("brief.md" in line and "house" in line for line in done.stdout.splitlines()
                            if "skipped scaffold candidate" in line), done.stdout)
        self.assertNotIn("WARN", done.stdout + done.stderr)

    def test_warning_from_failed_probe_is_discarded(self):
        self.write(self.root / "brief.md", "---\npdfmd-options: {kit: house}\n---\n")
        kit = self.root / "kits" / "house"
        self.write(kit / ".kit", "kit-format: 1\nname: house\nversion: 1\n"
                   "unknown-probe-key: ignored\ndefaults: defaults.yaml\n")
        self.write(kit / "defaults.yaml", "pdfmd-options: {parts: absent}\n")
        done, _ = self.build("paper.md", "--verbose")
        self.assertIn("skipped scaffold candidate", done.stdout)
        self.assertIn("brief.md", done.stdout)
        self.assertIn("not a folder", done.stdout)
        self.assertNotIn("WARN", done.stdout + done.stderr)
        quiet, _ = self.build()
        self.assertNotIn("brief.md", quiet.stdout + quiet.stderr)
        self.assertNotIn("unknown-probe-key", quiet.stdout + quiet.stderr)

    def test_bad_candidate_metadata_is_skipped(self):
        self.write(self.root / "brief.md", "---\npdfmd-options: {parts: auto}\n---\n")
        self.write(self.root / "metadata.yaml", "pdfmd-options: [broken\n")
        done, _ = self.build("paper.md", "--verbose")
        self.assertTrue(any("brief.md" in line and "expected" in line for line in done.stdout.splitlines()
                            if "skipped scaffold candidate" in line), done.stdout)
        self.assertNotIn("WARN", done.stdout + done.stderr)

    def test_failed_neighbour_probe_does_not_break_a_matching_scaffold(self):
        self.write(self.project / "report.md", "---\ntitle: Report\npdfmd-options: {parts: auto}\n---\n")
        self.write(self.project / "broken.md", "---\npdfmd-options: {kit: missing-kit}\n---\n")
        part = self.write(self.project / "parts" / "10-body.md", "# Body\n\nPart body.\n")
        for source in (str(part), "report.md"):
            with self.subTest(source=source):
                done, html = self.build(source, "--verbose")
                self.assertIn("Part body.", html)
                self.assertIn("Report", html)
                self.assertIn("skipped scaffold candidate", done.stdout)
                self.assertNotIn("WARN", done.stdout + done.stderr)

    def test_matching_kit_scaffold_still_supplies_settings_and_selected_parts(self):
        kit = self.root / "course" / "kits" / "house"
        self.write(kit / ".kit", "kit-format: 1\nname: house\nversion: 1\ndefaults: defaults.yaml\n")
        self.write(kit / "defaults.yaml", "pdfmd-options: {parts: chapters}\n")
        self.write(self.root / "course" / "report.md",
                   "---\ntitle: Scaffold title\npdfmd-options: {kit: house}\n---\n\nScaffold lead.\n")
        part = self.write(self.root / "course" / "chapters" / "10-first.md", "# First\n\nFirst body.\n")
        self.write(part.parent / "20-second.md", "# Second\n\nSecond body.\n")
        _, html = self.build(str(part), "--verbose")
        self.assertIn("Scaffold title", html)
        self.assertIn("Scaffold lead.", html)
        self.assertIn("First body.", html)
        self.assertNotIn("Second body.", html)
        _, whole = self.build("../report.md")
        self.assertIn("First body.", whole)
        self.assertIn("Second body.", whole)


if __name__ == "__main__":
    unittest.main()
