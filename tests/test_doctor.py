"""`pdfmd --doctor`: the one-page report, on a machine with everything missing and on this one."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent


def doctor(path: str, home: str, *extra: str) -> subprocess.CompletedProcess:
    environment = {**os.environ, "PATH": path, "PDFMD_NO_PROMPT": "1", "PDFMD_CONFIG": "",
                   "XDG_CONFIG_HOME": home, "XDG_CACHE_HOME": home, "XDG_DATA_HOME": home,
                   "LOCALAPPDATA": home, "APPDATA": home}
    return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--doctor", *extra], env=environment,
                          capture_output=True, text=True)


class DoctorTests(unittest.TestCase):
    def test_with_nothing_on_path_it_names_what_to_install(self):
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "empty"
            empty.mkdir()
            result = doctor(str(empty), directory)
            text = result.stdout
            self.assertIn("MISS  pandoc", text)
            self.assertIn("pdfmd --install pandoc", text)
            self.assertIn("MISS  tesseract", text)
            self.assertIn("thing(s) to fix", text)
            self.assertEqual(result.returncode, 0, result.stderr)   # a PDF can still be made

    def test_the_sections_are_there(self):
        with tempfile.TemporaryDirectory() as directory:
            text = doctor(os.environ.get("PATH", ""), directory).stdout
            for heading in ("Markdown to PDF:", "Fonts and scripts:", "Reading PDFs (PDF to Markdown):",
                            "Settings and cache:"):
                self.assertIn(heading, text)

    def test_deep_builds_a_page_with_the_built_in_renderer_when_nothing_else_is_there(self):
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "empty"
            empty.mkdir()
            result = doctor(str(empty), directory, "--deep")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Smoke test", result.stdout)
            self.assertRegex(result.stdout, r"(?m)^OK    (inkmd|md2pdf): built a PDF in ")

    def test_the_deep_page_has_a_struck_out_word(self):
        # ~~x~~ needs soul.sty on xelatex/pdflatex (lua-ul on lualatex): without it a missing package would pass the check
        sys.path.insert(0, str(ROOT))
        import pdfmd
        self.assertIn("~~", pdfmd.DEEP_SAMPLE)

    def test_deep_alone_is_refused(self):
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--deep"], capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("--deep goes with --doctor", done.stdout + done.stderr)

    def test_deep_says_why_an_engine_failed_and_stops_one_that_hangs(self):
        sys.path.insert(0, str(ROOT))
        import pdfmd
        failing = subprocess.CompletedProcess([], 1, "", "WARN  sample.md: typst failed (error: unknown font); no more engines to try.\n")
        with mock.patch.object(pdfmd.subprocess, "run", return_value=failing):
            self.assertEqual(pdfmd.deep_checks(["typst"]), [("typst", False, "error: unknown font")])
        with mock.patch.object(pdfmd.subprocess, "run", side_effect=subprocess.TimeoutExpired("x", 1)):
            self.assertEqual(pdfmd.deep_checks(["typst"], timeout=1), [("typst", False, "no answer after 1 s")])

    def test_deep_builds_an_ebook_for_an_entry_with_a_format(self):
        sys.path.insert(0, str(ROOT))
        import pdfmd

        def run(command, **kwargs):
            self.assertEqual(command[command.index("-e") + 1], "calibre")
            self.assertEqual(command[command.index("-o") + 1], "calibre.azw3")
            (Path(kwargs["cwd"]) / "calibre.azw3").write_bytes(b"BOOKMOBI")
            return subprocess.CompletedProcess(command, 0, "", "")
        with mock.patch.object(pdfmd.subprocess, "run", side_effect=run):
            (result,) = pdfmd.deep_checks(["calibre:azw3"])
        self.assertEqual(result[:2], ("calibre:azw3", True))


class ForeignCommands(unittest.TestCase):
    """v3.30.41: `--doctor` names a command of pdfmd's (`mdpdf`, `md2pdf` ...) that another program answers on the PATH."""

    def distribution(self, root: Path, names=("pdfmd", "mdpdf", "md2pdf")):
        from types import SimpleNamespace
        files = [PurePosixPath("bin") / name for name in names] + [PurePosixPath("pdfmd.py")]
        return SimpleNamespace(entry_points=[SimpleNamespace(name=name, group="console_scripts") for name in names],
                               files=files, locate_file=lambda file: root / file)

    def found(self, root: Path, on_path: dict[str, Path]):
        sys.path.insert(0, str(ROOT))
        import pdfmd
        with mock.patch.object(pdfmd.importlib.metadata, "distribution", lambda name: self.distribution(root)), \
                mock.patch.object(pdfmd, "which", lambda name: str(on_path[name]) if name in on_path else None):
            return pdfmd.foreign_commands()

    def test_a_name_answered_by_another_program_is_named(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bin").mkdir()
            elsewhere = root / "other"
            elsewhere.mkdir()
            for name in ("pdfmd", "mdpdf", "md2pdf"):
                (root / "bin" / name).write_text("#!/bin/sh\n", encoding="utf-8")
            (elsewhere / "md2pdf").write_text("#!/bin/sh\n", encoding="utf-8")
            result = self.found(root, {"pdfmd": root / "bin" / "pdfmd", "mdpdf": root / "bin" / "mdpdf",
                                       "md2pdf": elsewhere / "md2pdf"})
        self.assertEqual(result, [("md2pdf", str(elsewhere / "md2pdf"))])

    def test_names_that_are_ours_or_not_on_the_path_say_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bin").mkdir()
            (root / "bin" / "pdfmd").write_text("#!/bin/sh\n", encoding="utf-8")
            self.assertEqual(self.found(root, {"pdfmd": root / "bin" / "pdfmd"}), [])

    def test_a_checkout_without_the_package_says_nothing(self):
        sys.path.insert(0, str(ROOT))
        import pdfmd

        def missing(name):
            raise pdfmd.importlib.metadata.PackageNotFoundError(name)

        with mock.patch.object(pdfmd.importlib.metadata, "distribution", missing):
            self.assertEqual(pdfmd.foreign_commands(), [])


if __name__ == "__main__":
    unittest.main()
