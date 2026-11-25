"""Console diagnostics go through pdfmd_log.emit."""

import ast
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC = re.compile(r"^\s*(?:WARN|NOTE|ERROR|FOUND|DEFAULTS|AUTO|OK|FAIL|\[WARNING\])(?:\s|:|$)")


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


if __name__ == "__main__":
    unittest.main()
