"""A citation style named by its URL (v3.27.27): pdfmd fetches it once and keeps it, so a Pandoc built without HTTP
support ("pandoc was compiled without HTTP support") and a build with no network still work; offline it takes the
copy it fetched before, else a style of the same name in Pandoc's own csl/ folder, else Pandoc's default style
(`csl-fallback: default`) or an error (`csl-fallback: error`)."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")

import pdfmd  # noqa: E402

URL = "http://127.0.0.1:9/styles/ieee.csl"       # port 9 refuses at once: no network needed, none used
STYLE = ('<?xml version="1.0" encoding="utf-8"?>\n<style xmlns="http://purl.org/net/xbiblio/csl" class="in-text" '
         'version="1.0"><info><title>Test</title></info></style>\n')


class Folder(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-remote-csl-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        patcher = mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.directory / "cache"),
                                               "LOCALAPPDATA": str(self.directory / "cache")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, name: str, text: str) -> Path:
        path = self.directory / name
        path.write_text(text, encoding="utf-8")
        return path

    def resolve(self, doc: Path, **patches) -> tuple[Path | None, str]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out), \
                mock.patch.object(pdfmd, "fetch_csl", patches.get("fetch", lambda url: (None, "refused"))), \
                mock.patch.object(pdfmd, "pandoc_user_data_dir", lambda: patches.get("data_dir")):
            local = pdfmd.remote_csl(URL, doc, [])
        return local, out.getvalue()


class WhichStyle(Folder):
    def test_the_front_matter_then_the_winning_metadata_file(self):
        doc = self.write("a.md", f"---\ncsl: {URL}\n---\n\nText.\n")
        plain = self.write("b.md", "Text.\n")
        first = self.write("first.yaml", "csl: first.csl\n")
        second = self.write("second.yaml", "csl: second.csl\n")
        self.assertEqual(pdfmd.document_csl([doc], [first]), URL)
        self.assertEqual(pdfmd.document_csl([plain], [first, second]), "second.csl")
        self.assertIsNone(pdfmd.document_csl([plain], []))

    def test_nothing_for_a_local_style_one_the_command_line_names_or_no_auto(self):
        local = self.write("a.md", "---\ncsl: ieee.csl\n---\n\nText.\n")
        remote = self.write("b.md", f"---\ncsl: {URL}\n---\n\nText.\n")
        self.assertEqual(pdfmd.csl_args([local], [], [], None), [])
        for options in (["--csl", "mine.csl"], ["--csl=mine.csl"], ["-M", "csl=mine.csl"], ["--metadata=csl:mine.csl"]):
            self.assertEqual(pdfmd.csl_args([remote], [], options, None), [], options)
        self.assertEqual(pdfmd.csl_args([remote], [], [], ["remotecsl"]), [])


class Fetching(Folder):
    def test_fetched_once_and_kept(self):
        doc = self.write("a.md", "Text.\n")
        local, out = self.resolve(doc, fetch=lambda url: (STYLE, ""))
        self.assertEqual(local.read_text(encoding="utf-8"), STYLE)
        self.assertTrue(local.name.endswith("-ieee.csl"))
        self.assertIn("AUTO CSL", out)
        again, out = self.resolve(doc, fetch=lambda url: self.fail("fetched again"))
        self.assertEqual(again, local)

    def test_offline_the_old_copy(self):
        doc = self.write("a.md", "Text.\n")
        local, _ = self.resolve(doc, fetch=lambda url: (STYLE, ""))
        old = time.time() - 60 * 86400
        os.utime(local, (old, old))
        again, out = self.resolve(doc)
        self.assertEqual(again, local)
        self.assertIn("using the copy fetched on", out)
        self.assertNotIn("WARN", out)

    def test_then_pandocs_own_style_of_the_same_name(self):
        doc = self.write("a.md", "Text.\n")
        (self.directory / "data" / "csl").mkdir(parents=True)
        own = self.write("data/csl/ieee.csl", STYLE)
        local, out = self.resolve(doc, data_dir=self.directory / "data")
        self.assertEqual(local, own)
        self.assertIn("WARN", out)
        self.assertIn("Pandoc's own", out)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_then_pandocs_default_style_or_an_error(self):
        doc = self.write("a.md", "Text.\n")
        local, out = self.resolve(doc, data_dir=self.directory / "empty")
        self.assertEqual(local.name, "pandoc-default.csl")
        self.assertIn("<style", local.read_text(encoding="utf-8"))
        self.assertIn("Pandoc's default style", out)
        strict = self.write("b.md", "---\npdfmd-options:\n  csl-fallback: error\n---\n\nText.\n")
        with self.assertRaises(SystemExit) as caught:
            self.resolve(strict, data_dir=self.directory / "empty")
        self.assertIn("could not be fetched", str(caught.exception))


class Certificates(unittest.TestCase):
    def test_a_python_without_certificates_retries_with_the_systems(self):
        # a python.org Python on macOS before "Install Certificates": every https fetch failed (found on prelab1)
        import ssl
        import urllib.error
        calls = []

        def urlopen(request, timeout=None, context=None):
            calls.append(context)
            if context is None:
                raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "CERTIFICATE_VERIFY_FAILED"))
            return io.BytesIO(STYLE.encode("utf-8"))

        bundle = next((path for path in pdfmd.CA_BUNDLES if os.path.isfile(path)), None)
        if bundle is None:
            self.skipTest("no system CA bundle here")
        with mock.patch.object(pdfmd.urllib.request, "urlopen", urlopen):
            text, why = pdfmd.fetch_csl(URL)
        self.assertEqual((text, why), (STYLE, ""))
        self.assertEqual(len(calls), 2)
        self.assertIsInstance(calls[1], ssl.SSLContext)

    def test_another_error_is_not_retried(self):
        import urllib.error
        with mock.patch.object(pdfmd.urllib.request, "urlopen", side_effect=urllib.error.URLError("refused")) as opened:
            self.assertEqual(pdfmd.fetch_csl(URL), (None, "refused"))
        self.assertEqual(opened.call_count, 1)


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Building(Folder):
    def test_a_build_with_an_unreachable_style_uses_pandocs_own(self):
        (self.directory / "data" / "pandoc" / "csl").mkdir(parents=True)
        default = subprocess.run(["pandoc", "--print-default-data-file", "default.csl"], capture_output=True,
                                 text=True).stdout
        self.write("data/pandoc/csl/ieee.csl", default)
        self.write("refs.bib", "@book{doe, author = {Doe, Jane}, title = {A Book}, year = {2020}, publisher = {P}}\n")
        self.write("a.md", f"---\ntitle: A\nbibliography: refs.bib\ncsl: {URL}\n---\n\nAs shown [@doe].\n")
        environment = {**os.environ, "XDG_DATA_HOME": str(self.directory / "data"), "PDFMD_NO_PROMPT": "1"}
        run = [sys.executable, str(ROOT / "pdfmd.py"), "a.md", "-o", "a.html", "--no-stamp", "--no-backup"]
        done = subprocess.run(run, cwd=self.directory, capture_output=True, text=True, env=environment)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Pandoc's own", done.stderr)
        self.assertIn("Doe", (self.directory / "a.html").read_text(encoding="utf-8"))
        before = subprocess.run([*run, "--no-auto", "remotecsl"], cwd=self.directory, capture_output=True, text=True,
                                env=environment)
        self.assertNotEqual(before.returncode, 0)              # what 3.27.26 did: Pandoc cannot reach the URL


if __name__ == "__main__":
    unittest.main()
