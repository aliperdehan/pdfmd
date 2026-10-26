"""A home, cache or document folder that cannot be written (a sandbox, a read-only container): the build still happens, with a
temporary folder in the place of what cannot be written, and one NOTE (not a WARN) says so."""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

PANDOC = shutil.which("pandoc")
ENGINES = [name for name in ("lualatex", "xelatex", "pdflatex", "tectonic", "typst") if shutil.which(name)]
IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0
DOCUMENT = "---\ntitle: T\n---\n\nHello.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"


def clean_places():
    """Forget the temporary places a test made (they are removed when the process ends; here, now)."""
    for folder in pdfmd.TEMPORARY_PLACES.values():
        shutil.rmtree(folder, ignore_errors=True)
    pdfmd.TEMPORARY_PLACES.clear()
    pdfmd.NOTED_PLACES.clear()


class Scratch(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-readonly-"))
        self.addCleanup(self.remove)
        self.blocked = self.directory / "a-file"             # nothing can be made under a regular file, as root too
        self.blocked.write_text("not a folder\n", encoding="utf-8")

    def remove(self):
        for path in [self.directory, *self.directory.rglob("*")]:
            if path.is_dir() and not path.is_symlink():
                path.chmod(0o755)
        shutil.rmtree(self.directory, ignore_errors=True)


class Places(Scratch):
    def setUp(self):
        super().setUp()
        clean_places()
        self.addCleanup(clean_places)

    def test_what_is_writable(self):
        self.assertTrue(pdfmd.folder_is_writable(self.directory))
        self.assertTrue(pdfmd.folder_is_writable(self.directory / "not" / "there" / "yet"))      # the nearest folder above it
        self.assertFalse(pdfmd.folder_is_writable(self.blocked))
        self.assertFalse(pdfmd.folder_is_writable(self.blocked / "home" / ".cache"))

    @unittest.skipIf(IS_ROOT or sys.platform == "win32", "needs a user whose permissions count")
    def test_a_read_only_folder_is_not_writable(self):
        folder = self.directory / "ro"
        folder.mkdir()
        folder.chmod(0o555)
        self.assertFalse(pdfmd.folder_is_writable(folder))
        self.assertFalse(pdfmd.folder_is_writable(folder / "deeper"))

    def provide(self, **environment) -> str:
        """pdfmd.provide_writable_places() twice with an unwritable cache; the environment it left is in self.after."""
        variable = "LOCALAPPDATA" if sys.platform == "win32" else "XDG_CACHE_HOME"
        with mock.patch.dict(os.environ, {variable: str(self.blocked / "cache"), **environment}):
            with contextlib.redirect_stderr(io.StringIO()) as seen:
                pdfmd.provide_writable_places()
                pdfmd.provide_writable_places()                                # a second call says nothing more
            cache = pdfmd.cache_root()
            self.assertTrue(pdfmd.folder_is_writable(cache), cache)           # while the variable is still the temporary one
            self.assertTrue(str(cache).startswith(str(pdfmd.TEMPORARY_PLACES["cache"])))
            self.after = dict(os.environ)
        return seen.getvalue()

    def test_an_unwritable_cache_goes_to_a_temporary_folder_with_one_note(self):
        said = self.provide()
        self.assertEqual(said.count("NOTE  "), 1, said)
        self.assertNotIn("WARN", said)
        self.assertIn("cannot be written", said)
        self.assertTrue(pdfmd.TEMPORARY_PLACES["cache"].is_dir())

    def test_the_tex_user_tree_follows_when_the_home_cannot_be_written(self):
        if not any(shutil.which(name) for name in ("lualatex", "xelatex", "pdflatex", "latexmk", "tectonic")):
            self.skipTest("needs a TeX engine")
        home = {"HOME": str(self.blocked / "home"), "USERPROFILE": str(self.blocked / "home")}
        with mock.patch.dict(os.environ, home):
            os.environ.pop("TEXMFVAR", None)
            said = self.provide()
            self.assertTrue(self.after["TEXMFVAR"].startswith(str(pdfmd.TEMPORARY_PLACES["texmf"])))
            self.assertIn("TeX user tree", said)
            self.assertEqual(said.count("NOTE  "), 1, said)

    def test_a_writable_home_changes_nothing(self):
        variable = "LOCALAPPDATA" if sys.platform == "win32" else "XDG_CACHE_HOME"
        with mock.patch.dict(os.environ, {variable: str(self.directory / "cache"), "HOME": str(self.directory),
                                          "USERPROFILE": str(self.directory)}):
            os.environ.pop("TEXMFVAR", None)
            with contextlib.redirect_stderr(io.StringIO()) as seen:
                pdfmd.provide_writable_places()
            self.assertEqual(os.environ[variable], str(self.directory / "cache"))
            self.assertNotIn("TEXMFVAR", os.environ)
        self.assertEqual(seen.getvalue(), "")
        self.assertEqual(pdfmd.TEMPORARY_PLACES, {})

    def test_pandoc_runs_in_the_documents_folder_or_in_a_temporary_one(self):
        self.assertEqual(pdfmd.pandoc_working_directory(self.directory), self.directory)
        with contextlib.redirect_stderr(io.StringIO()) as seen:
            made = pdfmd.pandoc_working_directory(self.blocked / "folder")
            again = pdfmd.pandoc_working_directory(self.blocked / "folder")
        self.assertEqual(made, again)
        self.assertTrue(made.is_dir())
        self.assertEqual(seen.getvalue().count("NOTE  "), 1)
        self.assertIn("Pandoc runs in a temporary folder", seen.getvalue())

    def test_a_home_nobody_can_look_into_does_not_stop_the_import(self):
        done = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import pdfmd; print('imported')" % str(ROOT)],
                              capture_output=True, text=True, env={**os.environ, "HOME": str(self.blocked / "x"),
                                                                   "USERPROFILE": str(self.blocked / "x")})
        self.assertIn("imported", done.stdout, done.stderr)


@unittest.skipUnless(PANDOC and ENGINES, "needs Pandoc and a PDF engine")
class Builds(Scratch):
    """pdfmd itself, with HOME where nothing can be created and no XDG_* variable."""

    def environment(self, home: Path) -> dict:
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith("XDG_") and key not in ("TEXMFVAR", "TEXMFCONFIG", "PDFMD_CONFIG")}
        environment.update({"HOME": str(home), "USERPROFILE": str(home), "LOCALAPPDATA": str(home / "Local"),
                            "APPDATA": str(home / "Roaming"), "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                            "PYTHONDONTWRITEBYTECODE": "1"})
        if sys.platform == "win32":
            # pdfmd moves the cache folder (LOCALAPPDATA) when it cannot be written; MiKTeX keeps its configuration in APPDATA and
            # cannot run without a writable one, which has nothing to do with what is being tested
            environment["APPDATA"] = str(self.directory / "appdata")
            (self.directory / "appdata").mkdir(exist_ok=True)
        return environment

    def build(self, home: Path, *arguments: str, document: Path | None = None, cwd: Path | None = None):
        folder = self.directory / "work"
        folder.mkdir(exist_ok=True)
        if document is None:
            document = folder / "d.md"
            document.write_text(DOCUMENT, encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), str(document), "-e", ENGINES[0], "--no-backup", "--no-stamp",
                               *arguments], cwd=cwd or folder, capture_output=True, text=True, encoding="utf-8",
                              env=self.environment(home))
        return done

    @unittest.skipIf(sys.platform == "win32", "MiKTeX's LuaLaTeX stops in luaotfload when LOCALAPPDATA is not the folder it was set up with "
                     "(CI log of the portability PR); a read-only home is not how a Windows user meets this, and nothing here is Windows-specific")
    def test_a_home_under_a_file_still_builds_and_says_so_once(self):
        done = self.build(self.blocked / "home")
        self.assertTrue((self.directory / "work" / "d.pdf").is_file(), done.stdout + done.stderr)
        said = done.stdout + done.stderr
        self.assertEqual(said.count("cannot be written"), 1, said)
        self.assertIn("NOTE  the cache folder", said)
        self.assertNotRegex(said, r"WARN  [^\n]*(cache|cannot be written)")

    @unittest.skipIf(sys.platform == "win32", "MiKTeX's LuaLaTeX stops in luaotfload when LOCALAPPDATA is not the folder it was set up with "
                     "(CI log of the portability PR); a read-only home is not how a Windows user meets this, and nothing here is Windows-specific")
    def test_the_cache_options_do_not_crash_on_an_unwritable_cache(self):
        done = self.build(self.blocked / "home", "--cache", "--cache-plots")
        self.assertTrue((self.directory / "work" / "d.pdf").is_file(), done.stdout + done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    @unittest.skipIf(IS_ROOT or sys.platform == "win32", "needs a user whose permissions count")
    def test_a_read_only_home_stays_untouched(self):
        home = self.directory / "home"
        home.mkdir()
        home.chmod(0o555)
        done = self.build(home)
        self.assertTrue((self.directory / "work" / "d.pdf").is_file(), done.stdout + done.stderr)
        self.assertEqual(sorted(path.name for path in home.iterdir()), [])
        self.assertEqual((done.stdout + done.stderr).count("cannot be written"), 1)

    @unittest.skipIf(IS_ROOT or sys.platform == "win32", "needs a user whose permissions count")
    def test_a_read_only_document_folder_builds_with_what_it_names(self):
        source = self.directory / "readonly"
        source.mkdir()
        (source / "d.md").write_text("---\ntitle: T\nbibliography: refs.bib\n---\n\nCited [@knuth84].\n\n"
                                     "::: {.csv file=\"data.csv\"}\n:::\n", encoding="utf-8")
        (source / "data.csv").write_text("name,qty\nwater,3\n", encoding="utf-8")
        (source / "refs.bib").write_text("@book{knuth84, title={The TeXbook}, author={Knuth, Donald}, year={1984}}\n", encoding="utf-8")
        source.chmod(0o555)
        out = self.directory / "out"
        out.mkdir()
        done = self.build(self.directory / "home", "-o", str(out / "d.pdf"), document=source / "d.md", cwd=out)
        self.assertTrue((out / "d.pdf").is_file(), done.stdout + done.stderr)
        self.assertIn("Pandoc runs in a temporary folder", done.stdout + done.stderr)
        if shutil.which("pdftotext"):
            text = subprocess.run(["pdftotext", str(out / "d.pdf"), "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
            self.assertIn("water", text)                                       # data.csv, found beside the document
            self.assertIn("Knuth", text)                                       # refs.bib too
        self.assertEqual(sorted(path.name for path in source.iterdir()), ["d.md", "data.csv", "refs.bib"])


if __name__ == "__main__":
    unittest.main()
