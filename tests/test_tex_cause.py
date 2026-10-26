"""A failed TeX run names its cause when the log has a known signature (the signatures are from real logs of
a missing luaotfload, a missing package, a corrupt luaotfload database and an unwritable cache)."""
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

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

    def test_the_signature_is_found_across_a_wrapped_console_line(self):
        self.assertIn("writable", pdfmd.tex_failure_cause("luaotfload | load : FATAL ERROR\nsystem : no writeable cache\npath, quiting")[0])

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


CONSOLE = "luaotfload | load : FATAL ERROR\nluaotfload-init.lua:301: system : no writeable cache path, quiting\n"


class Probed(unittest.TestCase):
    """v3.30.35: Pandoc says only `Fatal error occurred` for a LuaTeX that cannot start; the cause is in its console."""

    def setUp(self):
        pdfmd.TEX_PROBES.clear()
        pdfmd.SHOWN_LOCATIONS.clear()

    def report(self, label, stderr="! ==> Fatal error occurred, no output PDF file produced!", engine="lualatex"):
        out = io.StringIO()
        with redirect_stderr(out):
            pdfmd.report_engine_failure(label, engine, failed(stderr), ["xelatex"], False)
        return out.getvalue()

    def test_a_bare_fatal_error_is_explained_by_a_probe_asked_once(self):
        probe = subprocess.CompletedProcess(["lualatex"], 1, CONSOLE, "")
        with mock.patch.object(pdfmd, "which", lambda name: "/bin/" + name), \
                mock.patch.object(pdfmd.subprocess, "run", return_value=probe) as run:
            first = self.report("probe-a.md")
            second = self.report("probe-b.md")
        self.assertIn("cause: the TeX cache folder is not writable; set TEXMFVAR and TEXMFCACHE", first)
        self.assertIn("cause:", second)
        self.assertEqual(run.call_count, 1)                      # one probe per run, not one per document

    def test_nothing_is_probed_when_the_text_already_says_or_another_engine_failed(self):
        with mock.patch.object(pdfmd, "which", lambda name: "/bin/" + name), mock.patch.object(pdfmd.subprocess, "run") as run:
            self.report("probe-c.md", "Fatal error occurred\n! LaTeX Error: File `soul.sty' not found.\n")
            self.report("probe-d.md", engine="xelatex")
            self.report("probe-e.md", "! Undefined control sequence.")
        run.assert_not_called()

    def test_a_probe_that_finds_nothing_says_nothing(self):
        healthy = subprocess.CompletedProcess(["lualatex"], 0, "Output written on probe.pdf", "")
        with mock.patch.object(pdfmd, "which", lambda name: "/bin/" + name), mock.patch.object(pdfmd.subprocess, "run", return_value=healthy):
            self.assertNotIn("cause:", self.report("probe-f.md"))

    @unittest.skipUnless(shutil.which("lualatex") and os.name == "posix" and (not hasattr(os, "geteuid") or os.geteuid() != 0),
                         "needs lualatex and a user who cannot write into a read-only folder")
    def test_a_real_lualatex_with_an_unwritable_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            locked = Path(directory) / "locked"
            locked.mkdir()
            locked.chmod(stat.S_IRUSR | stat.S_IXUSR)
            try:
                with mock.patch.dict(os.environ, {"TEXMFVAR": str(locked / "v"), "TEXMFCACHE": str(locked / "c")}):
                    found = pdfmd.probe_tex_cause("lualatex")
            finally:
                locked.chmod(stat.S_IRWXU)
        self.assertIsNotNone(found)
        self.assertIn("not writable", found[0])


if __name__ == "__main__":
    unittest.main()
