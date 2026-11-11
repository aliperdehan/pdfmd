"""DECISION 50: OpenDocument uses the Word route unless Pandoc is chosen."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd  # noqa: E402


class Route(unittest.TestCase):
    def setUp(self):
        state = mock.patch.dict(pdfmd.BUILD)
        state.start()
        self.addCleanup(state.stop)
        scratch = tempfile.TemporaryDirectory(prefix="pdfmd-odt-")
        self.addCleanup(scratch.cleanup)
        self.folder = Path(scratch.name)
        self.doc = self.folder / "doc.md"
        self.output = self.folder / "doc.odt"
        self.doc.write_text("Text.\n", encoding="utf-8")

    def build(self, engine=None, fail=False, options=(), cli=None, metadata=None):
        def pandoc(*args, **kwargs):
            # The real signature is retained by autospec; the route calls with keywords.
            values = pdfmd.inspect.signature(original).bind(*args, **kwargs).arguments
            path = values["output_file"]
            path.write_text(values["target_format"], encoding="utf-8")
            pdfmd.BUILD["output"] = path
            return self.doc, True, ""

        original = pdfmd._convert_one_core
        with mock.patch.object(pdfmd, "_convert_one_core", autospec=True, side_effect=pandoc) as writer, \
             mock.patch.object(pdfmd, "resolve_soffice", return_value=engine), \
             mock.patch.object(pdfmd, "run_soffice_convert", return_value=(not fail, "conversion failed")) as convert, \
             mock.patch.object(pdfmd, "ENGINE_CLI", cli), \
             mock.patch("sys.stderr") as stderr:
            result = pdfmd._convert_one(self.doc, None, False, "", [], [], None, list(options),
                                        output_file=self.output, target_format="odt", metadata_file=metadata)
        said = "".join(call.args[0] for call in stderr.write.call_args_list)
        return result, writer, convert, said

    def test_auto_uses_the_normal_word_build_and_existing_converter(self):
        result, writer, convert, said = self.build(engine="soffice")
        self.assertTrue(result[1])
        self.assertEqual(writer.call_args.kwargs["target_format"], "docx")
        self.assertEqual(convert.call_args.args[1:], (self.output, False, "odt"))
        self.assertFalse(convert.call_args.args[0].exists())  # intermediate cleaned up
        self.assertEqual(pdfmd.BUILD["output"], self.output)
        self.assertNotIn("WARN", said)

    def test_auto_missing_or_failed_warns_once_and_uses_pandoc(self):
        for engine, fail in ((None, False), ("soffice", True)):
            with self.subTest(engine=engine, fail=fail):
                result, writer, convert, said = self.build(engine=engine, fail=fail)
                self.assertTrue(result[1])
                self.assertEqual(writer.call_args.kwargs["target_format"], "odt")
                self.assertEqual(said.count("WARN"), 1)
                for words in ("raw Word blocks", "cover", "form", "Word route's extras", "install LibreOffice"):
                    self.assertIn(words, said)
                self.assertEqual(convert.call_count, int(engine is not None))

    def test_explicit_pandoc_is_silent_and_soffice_missing_is_an_error(self):
        self.doc.write_text("---\npdfmd-options: {odt: {engine: pandoc}}\n---\nText.\n")
        result, writer, convert, said = self.build()
        self.assertTrue(result[1])
        self.assertFalse(convert.called)
        self.assertNotIn("WARN", said)
        self.doc.write_text("---\npdfmd-options: {odt: {engine: soffice}}\n---\nText.\n")
        with self.assertRaisesRegex(SystemExit, "LibreOffice.*not found"):
            self.build()

    def test_cli_wins_and_forced_conversion_failure_is_an_error(self):
        self.doc.write_text("---\npdfmd-options: {odt: {engine: pandoc}}\n---\nText.\n")
        _, writer, convert, _ = self.build(engine="soffice", cli="soffice")
        self.assertTrue(convert.called)
        self.assertEqual(writer.call_args.kwargs["target_format"], "docx")
        with self.assertRaisesRegex(SystemExit, "conversion failed"):
            self.build(engine="soffice", cli="soffice", fail=True)
        self.doc.write_text("---\npdfmd-options: {odt: {engine: soffice}}\n---\nText.\n")
        _, writer, convert, said = self.build(cli="pandoc")
        self.assertFalse(convert.called)
        self.assertEqual(writer.call_args.kwargs["target_format"], "odt")
        self.assertNotIn("WARN", said)

    def test_metadata_engine_and_invalid_engine(self):
        metadata = self.folder / "settings.yaml"
        metadata.write_text("pdfmd-options: {odt: {engine: soffice}}\n")
        with self.assertRaisesRegex(SystemExit, "LibreOffice.*not found"):
            self.build(metadata=[metadata])
        self.doc.write_text("---\npdfmd-options: {odt: {engine: invalid}}\n---\nText.\n")
        with self.assertRaisesRegex(SystemExit, "odt.engine must be auto, soffice or pandoc"):
            self.build()

    def test_auto_reference_selects_pandoc_even_with_libreoffice(self):
        for options, name in (([], "reference.ott"), (["--reference-doc=chosen.odt"], "chosen.odt")):
            with self.subTest(name=name):
                (self.folder / name).touch()
                _, writer, convert, said = self.build(engine="soffice", options=options)
                self.assertEqual(writer.call_args.kwargs["target_format"], "odt")
                self.assertFalse(convert.called)
                self.assertIn("NOTE", said)
                self.assertIn(name, said)
                self.assertNotIn("WARN", said)

    def test_word_route_cannot_overwrite_its_source(self):
        self.output = self.doc
        with self.assertRaisesRegex(SystemExit, "source itself"):
            self.build(engine="soffice")
        self.assertEqual(self.doc.read_text(), "Text.\n")


@unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
class Launcher(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="pdfmd-odt-launcher-")
        self.addCleanup(scratch.cleanup)
        self.folder = Path(scratch.name)
        self.env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                    **{"XDG_" + key + "_HOME": str(self.folder / key.lower()) for key in ("CONFIG", "CACHE", "DATA")},
                    "APPDATA": str(self.folder / "config"), "LOCALAPPDATA": str(self.folder / "cache")}
        self.write()

    def write(self, settings="", timeout=0):
        (self.folder / "doc.md").write_text(
            f"---\npdfmd-options:\n  soffice-timeout: {timeout}\n" + settings + "---\n\nDistinctive zebra.\n\n"
            "```{=openxml}\n<w:p><w:r><w:t>RAW COVER</w:t></w:r></w:p>\n```\n", encoding="utf-8")

    def run_pdfmd(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), "doc.md", "-o", "doc.odt",
                               "--no-stamp", "--no-backup", "--no-auto", "font", *args],
                              cwd=self.folder, env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)

    def check_odt(self, done):
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        with zipfile.ZipFile(self.folder / "doc.odt") as archive:
            self.assertEqual(archive.read("mimetype"), b"application/vnd.oasis.opendocument.text")
            self.assertIn(b"Distinctive zebra", archive.read("content.xml"))

    def test_auto_without_soffice_warns_once(self):
        done = self.run_pdfmd()
        self.check_odt(done)
        self.assertEqual(done.stderr.count("WARN"), 1, done.stderr)
        self.assertIn("install LibreOffice", done.stderr)

    def test_pandoc_and_cli_override_have_no_warning(self):
        self.write("  odt: {engine: pandoc}\n")
        done = self.run_pdfmd()
        self.check_odt(done)
        self.assertNotIn("WARN", done.stderr)
        self.write("  odt: {engine: soffice}\n")
        done = self.run_pdfmd("-e", "pandoc")
        self.check_odt(done)
        self.assertNotIn("WARN", done.stderr)

    def test_forced_soffice_missing_is_an_error(self):
        self.write("  odt: {engine: soffice}\n")
        done = self.run_pdfmd()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("LibreOffice", done.stderr)
        self.assertFalse((self.folder / "doc.odt").exists())

    def test_ott_reference_selects_pandoc_with_a_note(self):
        done = subprocess.run([shutil.which("pandoc"), "--print-default-data-file=reference.odt"],
                              cwd=self.folder, env=self.env, stdin=subprocess.DEVNULL, capture_output=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        (self.folder / "reference.ott").write_bytes(done.stdout)
        done = self.run_pdfmd()
        self.check_odt(done)
        self.assertIn("NOTE", done.stderr)
        self.assertIn("Pandoc", done.stderr)
        self.assertIn("reference.ott", done.stderr)
        self.assertNotIn("WARN", done.stderr)
        reference = self.folder / "custom.ott"
        (self.folder / "reference.ott").rename(reference)
        self.write("  office: {reference-doc: custom.ott}\n")
        done = self.run_pdfmd()
        self.check_odt(done)
        self.assertIn("custom.ott", done.stderr)
        self.assertNotIn("WARN", done.stderr)

    def test_setup_folder_engine_and_default_output(self):
        setup = self.folder / ".pdfmd"
        setup.mkdir()
        (setup / "config.yaml").write_text("options: {odt: {engine: pandoc}}\n")
        done = self.run_pdfmd()
        self.check_odt(done)
        self.assertNotIn("WARN", done.stderr)
        self.write("  default-output: odt\n")
        done = subprocess.run([sys.executable, str(ROOT / "scripts/pdfmd"), "doc.md", "--no-stamp", "--no-backup"],
                              cwd=self.folder, env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.check_odt(done)
        self.assertNotIn("WARN", done.stderr)

    @unittest.skipIf(os.name == "nt", "POSIX stand-in for LibreOffice")
    def test_auto_with_soffice_uses_word_and_failed_conversion_falls_back(self):
        binary = self.folder / "soffice"
        log = self.folder / "word.json"
        binary.write_text("#!" + sys.executable + "\n" +
                          "import json, pathlib, sys, zipfile\n"
                          "source = pathlib.Path(sys.argv[-1])\n"
                          "with zipfile.ZipFile(source) as z: text = z.read('word/document.xml').decode()\n"
                          f"pathlib.Path({str(log)!r}).write_text(json.dumps(text))\n"
                          "out = pathlib.Path(sys.argv[sys.argv.index('--outdir') + 1])\n"
                          "(out / (source.stem + '.odt')).write_bytes(source.read_bytes())\n", encoding="utf-8")
        binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
        self.env["PATH"] = str(self.folder) + os.pathsep + self.env.get("PATH", "")
        self.write(timeout=-1)
        done = self.run_pdfmd()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue(log.exists(), done.stdout + done.stderr)
        self.assertIn("RAW COVER", json.loads(log.read_text()))
        self.assertNotIn("WARN", done.stderr)
        self.write("  odt: {engine: pandoc}\n", timeout=-1)
        done = self.run_pdfmd("-e", "soffice")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("RAW COVER", json.loads(log.read_text()))
        self.write(timeout=-1)
        binary.write_text("#!" + sys.executable + "\nraise SystemExit(1)\n")
        done = self.run_pdfmd()
        self.check_odt(done)
        self.assertEqual(done.stderr.count("WARN"), 1, done.stderr)

    def test_real_libreoffice_preserves_raw_word_blocks(self):
        if os.environ.get("CODEX_SANDBOX"):
            self.skipTest("LibreOffice cannot start in the Codex sandbox; run outside it")
        binary = pdfmd.resolve_soffice()
        if not binary:
            self.skipTest("needs LibreOffice")
        # A real conversion probes startup, using only files in this test's scratch folder.
        source = self.folder / "probe.docx"
        made = subprocess.run([shutil.which("pandoc"), "-f", "markdown", "-t", "docx", "-o", str(source)],
                              input="Probe.", cwd=self.folder, env=self.env, capture_output=True, text=True)
        self.assertEqual(made.returncode, 0, made.stderr)
        with mock.patch.object(pdfmd, "SOFFICE_TIMEOUT_NOW", pdfmd.SOFFICE_TIMEOUT):
            ok, reason = pdfmd.run_soffice_convert(source, self.folder / "probe.odt", False, "odt")
        if not ok:
            self.skipTest("LibreOffice fails to start/convert: " + reason)
        self.write(timeout=pdfmd.SOFFICE_TIMEOUT)
        done = self.run_pdfmd()
        self.check_odt(done)
        self.assertNotIn("WARN", done.stderr)
        with zipfile.ZipFile(self.folder / "doc.odt") as archive:
            self.assertIn(b"RAW COVER", archive.read("content.xml"))


if __name__ == "__main__":
    unittest.main()
