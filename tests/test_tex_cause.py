"""A failed TeX run names its cause when the log has a known signature (the signatures are from real logs of
a missing luaotfload, a missing package, a corrupt luaotfload database and an unwritable cache)."""
import io
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pdfmd  # noqa: E402


def failed(stderr):
    return subprocess.CompletedProcess(["pandoc"], 1, "", stderr)


class Causes(unittest.TestCase):
    def test_a_missing_package_names_it_and_where_it_comes_from(self):
        cause, fix = pdfmd.tex_failure_cause("Error producing PDF.\n! LaTeX Error: File `soul.sty' not found.\n")
        self.assertEqual(cause, "the LaTeX package soul.sty is missing")
        self.assertIn("tlmgr install soul", fix)
        self.assertIn("texlive-plain-generic", fix)

    def test_an_unknown_package_still_gets_a_tlmgr_line(self):
        self.assertIn("tlmgr install nosuch)", pdfmd.tex_failure_cause("! LaTeX Error: File `nosuch.sty' not found.")[1])

    def test_a_missing_luaotfload(self):
        text = "! Font \\TU/lmr/m/n/10=[lmroman10-regular]:+tlig; at 10pt not loadable: metric da\nta not found or bad."
        self.assertIn("luaotfload", pdfmd.tex_failure_cause(text)[0])

    def test_a_corrupt_database_and_an_unwritable_cache(self):
        corrupt = pdfmd.tex_failure_cause('luaotfload-database.lua:537: [string "t"]:1: unexpected symbol near <eof>')
        self.assertIn("corrupt", corrupt[0])
        self.assertIn("writable", pdfmd.tex_failure_cause("system : no writeable cache path, quitting")[0])

    def test_an_ordinary_error_is_not_classified(self):
        self.assertIsNone(pdfmd.tex_failure_cause("! Undefined control sequence.\nl.12 \\nosuchmacro"))


class Reported(unittest.TestCase):
    def report(self, stderr, label):
        out = io.StringIO()
        with redirect_stderr(out):
            pdfmd.report_engine_failure(label, "xelatex", failed(stderr), ["pdflatex"], False)
        return out.getvalue()

    def test_the_cause_is_printed_once_per_document(self):
        stderr = "Error producing PDF.\n! LaTeX Error: File `lmodern.sty' not found.\n"
        first = self.report(stderr, "cause-doc-a.md")
        self.assertIn("cause: the LaTeX package lmodern.sty is missing; install it (tlmgr install lmodern", first)
        self.assertNotIn("cause:", self.report(stderr, "cause-doc-a.md"))        # the next engine fails the same way
        self.assertIn("cause:", self.report(stderr, "cause-doc-b.md"))


if __name__ == "__main__":
    unittest.main()
