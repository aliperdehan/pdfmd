"""v3.29.7: `pdfmd --install core:tex` (also `cortex`): Pandoc and Tectonic. No test downloads anything."""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

NAMES = ["tectonic-0.17.0-aarch64-apple-darwin.tar.gz", "tectonic-0.17.0-x86_64-apple-darwin.tar.gz",
         "tectonic-0.17.0-x86_64-unknown-linux-gnu.tar.gz", "tectonic-0.17.0-x86_64-unknown-linux-musl.tar.gz",
         "tectonic-0.17.0-aarch64-unknown-linux-musl.tar.gz", "tectonic-0.17.0-x86_64-pc-windows-msvc.zip",
         "tectonic-0.17.0-x86_64-pc-windows-gnu.zip", "tectonic-0.17.0-x86_64.AppImage"]


def release(*names: str, digest: bool = True) -> dict:
    return {"assets": [{"name": name, "browser_download_url": f"https://example.invalid/{name}",
                        **({"digest": "sha256:" + "cd" * 32} if digest else {})} for name in names]}


class Assets(unittest.TestCase):
    def test_the_file_for_each_machine(self):
        cases = {("Darwin", "arm64"): "tectonic-0.17.0-aarch64-apple-darwin.tar.gz",
                 ("Darwin", "x86_64"): "tectonic-0.17.0-x86_64-apple-darwin.tar.gz",
                 ("Linux", "x86_64"): "tectonic-0.17.0-x86_64-unknown-linux-musl.tar.gz",
                 ("Linux", "aarch64"): "tectonic-0.17.0-aarch64-unknown-linux-musl.tar.gz",
                 ("Windows", "AMD64"): "tectonic-0.17.0-x86_64-pc-windows-msvc.zip"}
        for (system, machine), expected in cases.items():
            pattern = pdfmd.tectonic_asset_pattern(system, machine)
            found = pdfmd.release_asset_matching(pdfmd.TECTONIC_REPOSITORY, pattern, release(*NAMES))
            self.assertEqual(found[0], expected, (system, machine))

    def test_other_machines_have_none(self):
        self.assertIsNone(pdfmd.tectonic_asset_pattern("Linux", "riscv64"))

    def test_no_digest_no_file(self):
        pattern = pdfmd.tectonic_asset_pattern("Darwin", "arm64")
        self.assertIsNone(pdfmd.release_asset_matching(pdfmd.TECTONIC_REPOSITORY, pattern, release(*NAMES, digest=False)))


class Kinds(unittest.TestCase):
    def test_the_spellings(self):
        for value in ("core", "core:tex", "core:typst", "cortex"):
            self.assertEqual(pdfmd.install_kind(value), value)
        for value in ("core:docx", "cortex:tex", "calibre:x"):
            with self.assertRaises(Exception):
                pdfmd.install_kind(value)

    def test_each_is_sized(self):
        for kind in ("core", "cortex"):
            self.assertIn(kind, pdfmd.INSTALL_SIZES)

    def test_core_is_full_and_core_tex_is_pandoc_then_tectonic(self):
        calls: list[str] = []
        with mock.patch.object(pdfmd, "install_typst", lambda: calls.append("typst") or True), \
                mock.patch.object(pdfmd, "install_tectonic", lambda: calls.append("tectonic") or True), \
                mock.patch.object(pdfmd.subprocess, "run", lambda *a, **k: calls.append("pip") or mock.Mock(returncode=0, stderr="")), \
                contextlib.redirect_stdout(io.StringIO()):
            pdfmd.install_extra("core:tex")
            pdfmd.install_extra("cortex")
            self.assertEqual(calls.count("tectonic"), 2)
            self.assertNotIn("typst", calls)
            calls.clear()
            pdfmd.install_extra("core:typst")
            self.assertIn("typst", calls)
            self.assertNotIn("tectonic", calls)


class Install(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-tectonic-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        patch = mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(self.directory), "LOCALAPPDATA": str(self.directory)})
        patch.start()
        self.addCleanup(patch.stop)
        self.fetched: list[tuple[str, str]] = []

    def archive(self) -> Path:
        windows = pdfmd.platform.system().lower() == "windows"
        path = self.directory / ("t.zip" if windows else "t.tar.gz")
        script = b"#!/bin/sh\necho 'Tectonic 0.17.0'\n"
        if windows:
            with zipfile.ZipFile(path, "w") as bundle:
                bundle.writestr("tectonic.exe", script)
        else:
            with tarfile.open(path, "w:gz") as bundle:
                info = tarfile.TarInfo("tectonic")
                info.size = len(script)
                info.mode = 0o755
                bundle.addfile(info, io.BytesIO(script))
        return path

    def run_install(self, **kwargs):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            done = pdfmd.install_tectonic(**kwargs)
        return done, out.getvalue(), err.getvalue()

    @unittest.skipIf(sys.platform == "win32", "the stand-in is a shell script")
    def test_the_binary_lands_in_the_tools_folder_after_the_check(self):
        pattern = pdfmd.tectonic_asset_pattern()
        if pattern is None:
            self.skipTest("no Tectonic release for this machine")
        name = {"Darwin": "tectonic-0.17.0-{}-apple-darwin.tar.gz",
                "Linux": "tectonic-0.17.0-{}-unknown-linux-musl.tar.gz"}[pdfmd.platform.system()].format(
            "aarch64" if pdfmd.platform.machine().lower() in ("arm64", "aarch64") else "x86_64")
        source = self.archive()

        def fetch(url, destination, sha256):
            self.fetched.append((url, sha256))
            shutil.copyfile(source, destination)

        saved = os.environ["PATH"]
        self.addCleanup(os.environ.__setitem__, "PATH", saved)
        done, out, err = self.run_install(fetch=fetch, release=release(name))
        self.assertTrue(done, out + err)
        self.assertEqual(self.fetched, [(f"https://example.invalid/{name}", "cd" * 32)])
        self.assertIn("SHA-256 verified (cdcdcdcdcdcd", out)
        self.assertIn("Tectonic 0.17.0", out)
        self.assertTrue((pdfmd.tools_directory() / "tectonic").is_file())

    def test_no_digest_no_download(self):
        pattern = pdfmd.tectonic_asset_pattern()
        if pattern is None:
            self.skipTest("no Tectonic release for this machine")
        done, out, err = self.run_install(fetch=lambda *a: self.fetched.append(a), release=release(*NAMES, digest=False))
        self.assertFalse(done)
        self.assertEqual(self.fetched, [])
        self.assertIn("SHA-256", err)


if __name__ == "__main__":
    unittest.main()
