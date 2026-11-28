"""Console diagnostics go through pdfmd_log.emit."""

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC = re.compile(
    r"^\s*(?:(?:WARN|NOTE|ERROR|FOUND|DEFAULTS|AUTO|OK|FAIL|\[WARNING\])(?:\s|:|$)"
    r"|(?:ASSEMBLED|ATTACHED|EMBEDDED|HYBRID|KEPT|SPLIT|WATCH)  |PDF   )|^BACKUP  "
)


def leading_text(expression):
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        yield expression.value
    elif isinstance(expression, ast.JoinedStr) and expression.values:
        yield from leading_text(expression.values[0])
    elif isinstance(expression, ast.FormattedValue):
        yield from leading_text(expression.value)
    elif isinstance(expression, ast.IfExp):
        yield from leading_text(expression.body)
        yield from leading_text(expression.orelse)
    elif isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Add):
        yield from leading_text(expression.left)


class OutputSites(unittest.TestCase):
    def test_diagnostics_are_emitted(self):
        paths = [ROOT / "pdfmd.py", *(ROOT / "lib").rglob("*.py")]
        raw = []
        for path in paths:
            if {"pdfmd_inkmd", "pdfmd_yaml"}.intersection(path.parts):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call):
                    continue
                method = getattr(node.func, "id", getattr(node.func, "attr", None))
                offset = int(method == "vprint")
                if method in {"print", "vprint", "write"} and len(node.args) > offset:
                    if any(DIAGNOSTIC.match(text) for text in leading_text(node.args[offset])):
                        raw.append(f"{path.relative_to(ROOT)}:{node.lineno}")
        self.assertEqual(raw, [], "\n".join(raw))


class BuildRoutes(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.tex_cache = self.folder / "texmf-var"
        self.tex_cache.mkdir()

    def run_pdfmd(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "pdfmd"), *args],
            cwd=self.folder, env={**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                                  "TEXMFVAR": str(self.tex_cache), "TEXMFCACHE": str(self.tex_cache)},
            capture_output=True, encoding="utf-8", errors="replace", timeout=60,
        )

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_merge_progress_follows_chatter_and_reaches_the_log(self):
        (self.folder / "source.md").write_text("# Trial\n\nBody text.\n", encoding="utf-8")
        (self.folder / "metadata.yaml").write_text("title: Trial\n", encoding="utf-8")
        for level in ("normal", "result", "off"):
            with self.subTest(level=level):
                done = self.run_pdfmd("source.md", "--merge", "--chatter", level, "--log", f"{level}.log",
                                      "-o", f"{level}.md")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertIn("Body text.", (self.folder / f"{level}.md").read_text(encoding="utf-8"))
                self.assertEqual("OK    source.md" in done.stdout, level != "off")
                lines = (self.folder / f"{level}.log").read_text(encoding="utf-8").splitlines()
                for prefix in ("EMBEDDED ", "ASSEMBLED "):
                    self.assertEqual(sum(line.startswith(prefix) for line in lines), 1)
                    self.assertEqual(prefix in done.stdout, level == "normal")

    def test_check_lookup_errors_follow_chatter_and_count_in_summary(self):
        for command in ("--check", "--check-docx"):
            for level in ("warnings", "result", "off"):
                with self.subTest(command=command, level=level):
                    done = self.run_pdfmd("missing.md", command, "--summary", "--chatter", level)
                    self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                    self.assertEqual("missing.md" in done.stderr, level != "result")
                    self.assertEqual(done.stdout, "1 error\n" if level != "off" else "")


if __name__ == "__main__":
    unittest.main()
