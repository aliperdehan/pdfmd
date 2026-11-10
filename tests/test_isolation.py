"""The tests leave pdfmd's real cache, config and data folders alone (v3.33.60b): every test module imports isolation_support
first, which points them at a folder of the run's own and checks the real ones at the end of the process."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent


def first_imports(path: Path) -> list[str]:
    """The modules a test file imports, in order, up to its first statement that is not an import (or a docstring), plus the
    `sys.path.insert` lines it has before that."""
    names = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)                       # a test's own "\\." in a plain string
        tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
        elif isinstance(node, ast.Expr) and isinstance(node.value, (ast.Constant, ast.Call)):
            continue
        else:
            break
    return names


class EveryModule(unittest.TestCase):
    def test_every_test_module_imports_it_before_pdfmd_and_its_own_helpers(self):
        for path in sorted(TESTS.glob("test_*.py")):
            with self.subTest(path.name):
                names = first_imports(path)
                self.assertIn("isolation_support", names, f"{path.name}: `import isolation_support` with the stdlib imports")
                self.assertNotIn("pdfmd", names[:names.index("isolation_support")])


class TheRun(unittest.TestCase):
    def test_the_variables_point_at_the_runs_own_folder(self):
        self.assertTrue(Path(os.environ[isolation_support.MARK]).is_dir())
        self.assertTrue(isolation_support.REAL)
        for now in isolation_support.real_folders():                         # where pdfmd would look now
            with self.subTest(str(now)):
                self.assertNotIn(now, isolation_support.REAL)

    def test_a_process_that_writes_into_a_watched_folder_ends_with_status_1_and_names_it(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            code = ("import os, sys; sys.path.insert(0, %r); import isolation_support as i; "
                    "from pathlib import Path; Path(os.environ['WATCHED'], 'pdfmd', 'builds', 'x-1').mkdir(parents=True)" % str(TESTS))
            env = {key: value for key, value in os.environ.items() if key != isolation_support.MARK}
            env.update({"XDG_CACHE_HOME": str(base / "cache"), "XDG_CONFIG_HOME": str(base / "config"),
                        "XDG_DATA_HOME": str(base / "data"), "LOCALAPPDATA": str(base / "cache"), "APPDATA": str(base / "config"),
                        "WATCHED": str(base / "cache")})
            (base / "cache" / "pdfmd").mkdir(parents=True)
            done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
            self.assertEqual(done.returncode, 1, done.stderr)
            self.assertIn("wrote into pdfmd's real folders", done.stderr)
            self.assertIn("\n  " + str(base / "cache" / "pdfmd" / "builds" / "x-1") + "\n", done.stderr)
            quiet = subprocess.run([sys.executable, "-c", code.replace("os.environ['WATCHED']", "os.environ['XDG_CACHE_HOME']")],
                                   capture_output=True, text=True, env=env)
            self.assertEqual(quiet.returncode, 0, quiet.stderr)                  # the run's own cache: nothing to say
            self.assertEqual(quiet.stderr, "")

    def test_a_build_of_a_document_elsewhere_during_the_run_is_listed_apart(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            env = {key: value for key, value in os.environ.items() if key != isolation_support.MARK}
            env.update({"XDG_CACHE_HOME": str(base / "cache"), "XDG_CONFIG_HOME": str(base / "config"),
                        "XDG_DATA_HOME": str(base / "data"), "LOCALAPPDATA": str(base / "cache"), "APPDATA": str(base / "config")})
            (base / "cache" / "pdfmd").mkdir(parents=True)

            def run(name: str, document: str, extra: str = "") -> subprocess.CompletedProcess:
                code = ("import sys; sys.path.insert(0, %r); import isolation_support; from pathlib import Path; "
                        "record = Path(%r, 'pdfmd', 'builds', %r); record.mkdir(parents=True); "
                        "(record / '1-ok.log').write_text('pdfmd build record\\ndocument:  ' + %r + '\\n')%s"
                        % (str(TESTS), str(base / "cache"), name, document, extra))
                return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)

            elsewhere = run("report-1", str(Path.home() / "Documents" / "report.md"),
                            "; Path(%r, 'pdfmd', 'tex').mkdir()" % str(base / "cache"))         # and a file that names no document
            self.assertEqual(elsewhere.returncode, 0, elsewhere.stderr)
            self.assertIn("NOTE  pdfmd's real cache changed during the run by a build of a document outside the tests", elsewhere.stderr)
            self.assertIn("pdfmd/tex", elsewhere.stderr.replace(os.sep, "/"))
            self.assertNotIn("ERROR", elsewhere.stderr)
            if sys.platform != "win32" and os.path.realpath(tempfile.gettempdir()) != os.path.realpath("/tmp"):
                other = run("o-1", "/tmp/another-session/o.md")                              # another program's temporary folder
                self.assertEqual(other.returncode, 0, other.stderr)
                self.assertIn("NOTE  ", other.stderr)
            mine = run("d-1", str(base / "work" / "d.md"))                                      # a document in the tests' own
            self.assertEqual(mine.returncode, 1, mine.stderr)
            self.assertIn("ERROR  the test run wrote into pdfmd's real folders", mine.stderr)


if __name__ == "__main__":
    unittest.main()
