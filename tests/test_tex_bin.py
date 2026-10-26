"""Issue 15: a TeX that is installed but not on PATH (Windows: C:\\texlive\\2026\\bin\\windows) is found all the same."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pdfmd  # noqa: E402


def install(root: Path, year: str, arch: str, program: str = "lualatex.exe") -> Path:
    folder = root / year / "bin" / arch
    folder.mkdir(parents=True)
    (folder / program).write_text("", encoding="utf-8")
    return folder


class Finding(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pdfmd-texbin-"))
        self.addCleanup(__import__("shutil").rmtree, self.root, True)

    def test_the_newest_year_wins(self):
        install(self.root, "2024", "windows")
        newest = install(self.root, "2026", "windows")
        install(self.root, "2025", "windows")
        self.assertEqual(pdfmd.find_tex_directory([str(self.root / "*" / "bin" / "*")]), newest)

    def test_a_folder_without_an_engine_is_not_taken(self):
        install(self.root, "2026", "windows", program="tlmgr.exe")
        self.assertIsNone(pdfmd.find_tex_directory([str(self.root / "*" / "bin" / "*")]))

    def test_a_named_folder_is_found_as_it_is(self):
        folder = install(self.root, "2026", "x86_64-linux", program="xelatex")
        self.assertEqual(pdfmd.find_tex_directory([str(folder)]), folder)

    def test_nothing_there_is_none(self):
        self.assertIsNone(pdfmd.find_tex_directory([str(self.root / "nope" / "*")]))

    def test_the_windows_places_include_texlive_and_miktex(self):
        patterns = " ".join(pdfmd.tex_install_patterns("windows", {"SystemDrive": "C:", "ProgramFiles": "C:\\Program Files",
                                                                   "LOCALAPPDATA": "C:\\Users\\a\\AppData\\Local"}))
        self.assertIn("texlive", patterns)
        self.assertIn("MiKTeX", patterns)


class Using(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pdfmd-texbin-"))
        self.addCleanup(__import__("shutil").rmtree, self.root, True)
        self.folder = install(self.root, "2026", "windows")
        self.env = mock.patch.dict(os.environ, {"PATH": "/nowhere", "PDFMD_TEX_BIN": str(self.folder)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(setattr, pdfmd, "TEX_FOUND_AT", pdfmd.TEX_FOUND_AT)

    def test_with_no_tex_on_path_the_folder_goes_behind_it(self):
        pdfmd.TEX_FOUND_AT = None
        with mock.patch.object(pdfmd.shutil, "which", return_value=None):
            pdfmd.use_tex_install()
        self.assertEqual(pdfmd.TEX_FOUND_AT, self.folder)
        self.assertEqual(os.environ["PATH"], os.pathsep.join(["/nowhere", str(self.folder)]))

    def test_with_a_tex_on_path_nothing_is_changed(self):
        pdfmd.TEX_FOUND_AT = None
        with mock.patch.object(pdfmd.shutil, "which", return_value="/usr/bin/lualatex"):
            pdfmd.use_tex_install()
        self.assertIsNone(pdfmd.TEX_FOUND_AT)
        self.assertEqual(os.environ["PATH"], "/nowhere")


if __name__ == "__main__":
    unittest.main()
