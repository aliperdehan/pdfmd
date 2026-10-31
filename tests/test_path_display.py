"""v3.31.41: how a path is written in a message (entry 3ea): relative also above the working folder (up to `path-up` steps),
`~/...` under the home folder, the style a setting, --verbose no longer forcing full paths."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


class Display(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve() / "home"
        self.deep = self.home / "a" / "b" / "c" / "d"
        self.deep.mkdir(parents=True)
        (self.home / "a" / ".pdfmd").mkdir()
        self.settings = (".pdfmd/metadata.yaml",)
        for target in (self.home / "a" / ".pdfmd" / "metadata.yaml", self.home / "x.yaml", self.deep / "here.md"):
            target.write_text("k: v\n", encoding="utf-8")
        self.outside = Path(self.temporary.name).resolve() / "outside.yaml"
        self.outside.write_text("k: v\n", encoding="utf-8")
        saved = (pdfmd.SHOW_FULL_PATHS, pdfmd.PATH_STYLE, pdfmd.PATH_UP, Path.cwd())
        self.addCleanup(lambda: (setattr(pdfmd, "SHOW_FULL_PATHS", saved[0]), setattr(pdfmd, "PATH_STYLE", saved[1]),
                                 setattr(pdfmd, "PATH_UP", saved[2]), os.chdir(saved[3])))
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.home), "USERPROFILE": str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.chdir(self.deep)
        pdfmd.SHOW_FULL_PATHS, pdfmd.PATH_STYLE, pdfmd.PATH_UP = False, "auto", 2

    def shown(self, path: Path, style="auto", up=2) -> str:
        pdfmd.PATH_STYLE, pdfmd.PATH_UP = style, up
        return pdfmd.display_path(path).replace("\\", "/")

    def test_a_file_in_the_working_folder_is_relative(self):
        self.assertEqual(self.shown(self.deep / "here.md"), "here.md")

    def test_a_folder_above_is_written_with_dots_up_to_the_cap(self):
        self.assertEqual(self.shown(self.home / "a" / "b" / "c" / "x.md"), "../x.md")
        self.assertEqual(self.shown(self.home / "a" / "b" / "y.md"), "../../y.md")

    def test_beyond_the_cap_it_is_the_home_form_then_the_full_path(self):
        self.assertEqual(self.shown(self.home / "a" / ".pdfmd" / "metadata.yaml"), "~/a/.pdfmd/metadata.yaml")
        self.assertEqual(self.shown(self.home / "x.yaml"), "~/x.yaml")
        self.assertEqual(self.shown(self.outside), str(self.outside).replace("\\", "/"))
        self.assertEqual(self.shown(self.home / "a" / ".pdfmd" / "metadata.yaml", up=3), "../../../.pdfmd/metadata.yaml")

    def test_the_styles(self):
        far = self.home / "x.yaml"
        self.assertEqual(self.shown(far, "relative"), str(far).replace("\\", "/"))
        self.assertEqual(self.shown(far, "home"), "~/x.yaml")
        self.assertEqual(self.shown(self.deep / "here.md", "home"), "~/a/b/c/d/here.md")
        self.assertEqual(self.shown(far, "full"), str(far).replace("\\", "/"))
        pdfmd.SHOW_FULL_PATHS = True                                   # --full-paths
        self.assertEqual(self.shown(self.deep / "here.md"), str(self.deep / "here.md").replace("\\", "/"))

    def test_a_bad_style_or_cap_is_said(self):
        with mock.patch.object(pdfmd, "config_options", return_value={"path-style": "nearby"}):
            with self.assertRaises(SystemExit):
                pdfmd.path_style_settings(None)
        with mock.patch.object(pdfmd, "config_options", return_value={"path-up": "-1"}):
            with self.assertRaises(SystemExit):
                pdfmd.path_style_settings(None)
            with self.assertRaises(SystemExit):
                pdfmd.path_style_settings(None, -2)
        with mock.patch.object(pdfmd, "config_options", return_value={"path-style": "Home", "path-up": 3}):
            self.assertEqual(pdfmd.path_style_settings(None), ("home", 3))
            self.assertEqual(pdfmd.path_style_settings("full"), ("full", 3))
            self.assertEqual(pdfmd.path_style_settings(None, 0), ("home", 0))

    def test_verbose_gives_full_unless_a_style_is_asked_for(self):
        with mock.patch.object(pdfmd, "config_options", return_value={"path-style": "home"}):
            self.assertEqual(pdfmd.path_style_settings(None, verbose=True)[0], "full")
            self.assertEqual(pdfmd.path_style_settings("auto", verbose=True)[0], "auto")


def run_pdfmd(folder: Path, root: Path, *extra: str) -> str:
    env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_BUILD_LOG": "off", "XDG_CACHE_HOME": str(root / "cache")}
    done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "d.md", "--to", "tex", "-o", "o.tex", "--no-stamp",
                           "--no-backup", "--no-auto", "crossref", *extra], cwd=folder, capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr
    return (done.stdout + done.stderr).replace("\\", "/")


class Runs(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "course" / ".pdfmd").mkdir(parents=True)
        (self.root / "course" / ".pdfmd" / "metadata.yaml").write_text("author: X\n", encoding="utf-8")
        self.folder = self.root / "course" / "LR1"
        self.folder.mkdir()
        (self.folder / "d.md").write_text("---\ntitle: T\n---\n\nText.\n", encoding="utf-8")
        self.absolute = str(self.root).replace("\\", "/") + "/course/.pdfmd"

    def auto_lines(self, text: str) -> str:
        return "\n".join(line for line in text.splitlines() if line.startswith("AUTO"))

    def test_verbose_writes_full_paths_and_an_explicit_style_wins(self):
        verbose = run_pdfmd(self.folder, self.root, "--verbose")
        self.assertIn(self.absolute, self.auto_lines(verbose))
        short = run_pdfmd(self.folder, self.root, "--verbose", "--path-style", "auto")
        self.assertIn("../.pdfmd/metadata.yaml", short)
        self.assertNotIn(self.absolute, self.auto_lines(short))

    def test_a_run_without_verbose_writes_dots_and_path_up_is_a_flag(self):
        quiet = run_pdfmd(self.folder, self.root)
        self.assertNotIn(self.absolute, quiet)
        if "FOUND" in quiet or "AUTO" in quiet:
            self.assertIn("../.pdfmd", quiet)
        none = run_pdfmd(self.folder, self.root, "--path-up", "0", "--path-style", "relative", "--verbose")
        self.assertIn(self.absolute, self.auto_lines(none))

    def test_a_folders_own_settings_set_the_style(self):
        (self.root / "course" / ".pdfmd" / "config.yaml").write_text("options:\n  path-up: 0\n  path-style: relative\n", encoding="utf-8")
        with_folder = run_pdfmd(self.folder, self.root, "--path-style", "relative", "--verbose")
        self.assertIn(self.absolute, self.auto_lines(with_folder))        # path-up 0 from the folder: `..` is not allowed


if __name__ == "__main__":
    unittest.main()
