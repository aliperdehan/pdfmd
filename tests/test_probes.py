"""Version and capability probes (`pandoc --version`, `kpsewhich`, `typst --version` ...) have a timeout and a probe that does not
answer counts as "not available"; a command that builds something never has one."""

from __future__ import annotations

import ast
import contextlib
import io
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

import pdfmd  # noqa: E402

SLEEPS = [sys.executable, "-c", "import time; time.sleep(60)"]
PROBE_WORDS = {"--version", "--help", "-var-value", "--list-extensions", "--print-default-data-file"}


def calls_of_subprocess_run(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run" \
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
            yield node


def words_of(node: ast.AST) -> set[str]:
    found: set[str] = set()
    for part in ast.walk(node):
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            found.add(part.value.split("=")[0])
        elif isinstance(part, ast.JoinedStr):
            first = part.values[0] if part.values else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.add(first.value.split("=")[0])
    return found


class Helper(unittest.TestCase):
    def test_the_timeout_is_ten_seconds_and_named(self):
        self.assertEqual(pdfmd.PROBE_TIMEOUT, 10)

    def test_an_answer_is_returned(self):
        done = pdfmd.run_probe([sys.executable, "--version"])
        self.assertEqual(done.returncode, 0)
        self.assertIn("Python", done.stdout + done.stderr)

    def test_a_program_that_is_not_there_is_none(self):
        self.assertIsNone(pdfmd.run_probe(["pdfmd-no-such-program-anywhere", "--version"]))

    def test_a_probe_that_does_not_answer_is_none_after_the_timeout_with_a_verbose_line(self):
        with mock.patch.object(pdfmd, "PROBE_TIMEOUT", 1), mock.patch.object(pdfmd, "VERBOSE_OUTPUT", True):
            started = time.monotonic()
            with contextlib.redirect_stdout(io.StringIO()) as seen:
                self.assertIsNone(pdfmd.run_probe(SLEEPS))
            self.assertLess(time.monotonic() - started, 20)
        self.assertIn("AUTO PROBE", seen.getvalue())
        self.assertIn("no answer in 1 s; counted as not available", seen.getvalue())

    def test_without_verbose_it_is_silent(self):
        with mock.patch.object(pdfmd, "PROBE_TIMEOUT", 1), mock.patch.object(pdfmd, "VERBOSE_OUTPUT", False):
            with contextlib.redirect_stdout(io.StringIO()) as seen:
                self.assertIsNone(pdfmd.run_probe(SLEEPS))
        self.assertEqual(seen.getvalue(), "")


@unittest.skipIf(sys.platform == "win32", "a script named pandoc on PATH")
class HungProgram(unittest.TestCase):
    """A `pandoc` and a `kpsewhich` that never answer: pdfmd goes on as if they were not there."""

    def setUp(self):
        self.bin = Path(tempfile.mkdtemp(prefix="pdfmd-hung-"))
        for name in ("pandoc", "kpsewhich"):
            script = self.bin / name
            script.write_text("#!/bin/sh\nsleep 60\n", encoding="utf-8")
            script.chmod(script.stat().st_mode | stat.S_IEXEC)
        self.patches = [mock.patch.dict(os.environ, {"PATH": str(self.bin) + os.pathsep + os.environ["PATH"]}),
                        mock.patch.object(pdfmd, "PROBE_TIMEOUT", 1)]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(__import__("shutil").rmtree, self.bin, True)

    def test_the_pandoc_version_is_unknown(self):
        with mock.patch.object(pdfmd, "_PANDOC_VERSION", None):
            self.assertEqual(pdfmd.pandoc_version(), (0,))

    def test_what_pandoc_lists_is_empty(self):
        with mock.patch.dict(pdfmd._PANDOC_EXTENSIONS, clear=True):
            self.assertEqual(pdfmd.pandoc_extensions("markdown"), frozenset())

    def test_kpsewhich_finds_nothing(self):
        self.assertIsNone(pdfmd.kpsewhich_path("article.cls"))
        self.assertEqual(pdfmd.kpsewhich_locate(["article.cls"]), {})
        pdfmd.engine_version_line.cache_clear()
        self.assertEqual(pdfmd.engine_version_line(str(self.bin / "pandoc")), "")


class FontList(unittest.TestCase):
    def test_a_font_list_is_read_as_utf8_and_an_empty_answer_is_an_empty_set(self):
        pdfmd.installed_font_families.cache_clear()
        self.addCleanup(pdfmd.installed_font_families.cache_clear)
        answer = mock.Mock(stdout="Caf\u00e9 Serif,Caf\u00e9\nDejaVu Sans\n".encode("utf-8"))
        with mock.patch.object(pdfmd.shutil, "which", lambda name: "fc-list"), mock.patch.object(pdfmd.subprocess, "run", return_value=answer):
            self.assertEqual(pdfmd.installed_font_families(), frozenset({"caf\u00e9 serif", "caf\u00e9", "dejavu sans"}))
        pdfmd.installed_font_families.cache_clear()
        with mock.patch.object(pdfmd.shutil, "which", lambda name: "fc-list"), \
                mock.patch.object(pdfmd.subprocess, "run", return_value=mock.Mock(stdout=None)):
            self.assertEqual(pdfmd.installed_font_families(), frozenset())


class Source(unittest.TestCase):
    """Read from the code, so a probe added later without a timeout is found."""

    def test_every_version_or_capability_probe_has_a_timeout(self):
        missing = []
        for path in [ROOT / "pdfmd.py", *sorted(ROOT.glob("pdfmd_*/*.py"))]:
            if "pdfmd_inkmd" in path.parts:
                continue
            for node in calls_of_subprocess_run(path):
                if not node.args or not isinstance(node.args[0], (ast.List, ast.Tuple)):
                    continue
                if words_of(node.args[0]) & PROBE_WORDS and not any(keyword.arg == "timeout" for keyword in node.keywords):
                    missing.append(f"{path.name}:{node.lineno}")
        self.assertEqual(missing, [], "a probe without timeout= (use pdfmd.run_probe)")

    def test_no_build_command_has_one(self):
        # the functions that run Pandoc or a LaTeX engine to make the document
        wanted = {"run_tex_engine", "run_engine_command", "run_pandoc", "convert_one", "run_latex_pass"}
        tree = ast.parse((ROOT / "pdfmd.py").read_text(encoding="utf-8"))
        checked = 0
        for function in ast.walk(tree):
            if isinstance(function, ast.FunctionDef) and function.name in wanted:
                checked += 1
                for node in ast.walk(function):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run" \
                            and any(keyword.arg == "timeout" for keyword in node.keywords):
                        self.fail(f"{function.name}:{node.lineno}: a build command must not have a timeout")
        self.assertGreaterEqual(checked, 2)


class SubprocessDecoding(unittest.TestCase):
    def test_no_text_mode_call_leaves_the_decoding_to_the_console_code_page(self):
        """issue 13: `text=True` decodes with the ANSI code page on Windows; fc-list, Pandoc and TeX write UTF-8, and a byte
        the page cannot decode ended the reader thread and made `.stdout` None. Every call names its encoding."""
        import ast
        sources = [ROOT / "pdfmd.py", *sorted(ROOT.glob("pdfmd_*/*.py"))]
        bad = []
        for path in sources:
            if "pdfmd_inkmd" in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("run", "Popen", "check_output"):
                    names = {keyword.arg for keyword in node.keywords}
                    if ("text" in names or "universal_newlines" in names) and "encoding" not in names:
                        bad.append(f"{path.name}:{node.lineno}")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
