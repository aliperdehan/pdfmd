"""v3.28.33: `pdfmd --install diagram[:d2|:dot]`. The downloads are replaced here (a tarball made on the spot, the release
lookup answered by a function), so no network is used; node, where there is one, really runs the launchers."""

from __future__ import annotations

import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

NODE = shutil.which("node")


def tarball(path: Path, members: dict[str, bytes], mode: int = 0o644) -> None:
    with tarfile.open(path, "w:gz") as bundle:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = mode
            bundle.addfile(info, io.BytesIO(data))


FAKE_PACKAGE = {
    "package/LICENSE": b"Apache-2.0\n",
    "package/package.json": b'{"name": "@hpcc-js/wasm-graphviz", "type": "module"}\n',
    "package/dist/index.js": b"export const Graphviz = {load: async () => ({layout: (source, format, engine) => "
                             b"`<svg data-engine='${engine}' data-format='${format}'>${source.length}</svg>`})};\n",
    "package/dist/index.js.map": b"{}",
    "package/src/index.ts": b"",
}


class Names(unittest.TestCase):
    def test_d2_release_names_follow_the_machine(self):
        name = pdfmd.d2_asset_name
        self.assertEqual(name("v0.9.0", "Darwin", "arm64"), "d2-v0.9.0-macos-arm64.tar.gz")
        self.assertEqual(name("v0.9.0", "Darwin", "x86_64"), "d2-v0.9.0-macos-amd64.tar.gz")
        self.assertEqual(name("v0.9.0", "Linux", "aarch64"), "d2-v0.9.0-linux-arm64.tar.gz")
        self.assertEqual(name("v0.9.0", "Linux", "AMD64"), "d2-v0.9.0-linux-amd64.tar.gz")
        self.assertEqual(name("v0.9.0", "Windows", "AMD64"), "d2-v0.9.0-windows-amd64.tar.gz")
        self.assertIsNone(name("v0.9.0", "Linux", "riscv64"))

    def test_the_kinds_are_accepted_and_a_wrong_one_is_refused(self):
        for good in ("diagram", "diagram:d2", "diagram:dot"):
            self.assertEqual(pdfmd.install_kind(good), good)
        for bad in ("diagram:mermaid", "diagram:", "diagrams"):
            with self.assertRaises(Exception):
                pdfmd.install_kind(bad)
        self.assertIn("diagram", pdfmd.INSTALL_KINDS)
        self.assertIn("diagram", pdfmd.INSTALL_SIZES)


class Installs(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        patcher = unittest.mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "data"),
                                                       "LOCALAPPDATA": str(self.root / "data")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_download(self, members: dict[str, bytes], mode: int = 0o644):
        def download(url, destination, sha256):
            tarball(destination, members, mode)
        return download

    @unittest.skipIf(sys.platform == "win32", "a shell script stands in for the binary")
    def test_d2_is_downloaded_checked_and_put_in_the_tools_folder(self):
        release = {"tag_name": "v9.9.9", "assets": [
            {"name": pdfmd.d2_asset_name("v9.9.9"), "browser_download_url": "https://example.invalid/d2.tar.gz",
             "digest": "sha256:" + "0" * 64}]}
        script = b"#!/bin/sh\necho v9.9.9\n"
        seen = {}

        def download(url, destination, sha256):
            seen["sha256"] = sha256
            tarball(destination, {"d2-v9.9.9/bin/d2": script, "d2-v9.9.9/README.md": b"x"}, 0o755)

        with unittest.mock.patch.object(pdfmd, "github_latest_release", return_value=release), \
                unittest.mock.patch.object(pdfmd, "download_file", download), \
                unittest.mock.patch.object(pdfmd, "d2_asset_name", return_value=pdfmd.d2_asset_name("v9.9.9", "Darwin", "arm64")), \
                unittest.mock.patch.object(pdfmd, "which", return_value=None), \
                unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as shown:
            release["assets"][0]["name"] = pdfmd.d2_asset_name("v9.9.9")
            self.assertTrue(pdfmd.install_extra("diagram:d2"))
        self.assertEqual(seen["sha256"], "0" * 64)                                 # the digest GitHub lists is the one checked
        installed = pdfmd.tools_directory() / "d2"
        self.assertTrue(installed.is_file() and os.access(installed, os.X_OK))
        self.assertIn("SHA-256 verified", shown.getvalue())
        self.assertIn("Installed D2 v9.9.9", shown.getvalue())

    def test_a_release_without_this_machine_is_said_so(self):
        release = {"tag_name": "v9.9.9", "assets": []}
        with unittest.mock.patch.object(pdfmd, "github_latest_release", return_value=release), \
                unittest.mock.patch("sys.stderr", new_callable=io.StringIO) as said:
            self.assertFalse(pdfmd.install_d2())
        self.assertIn("No D2 release is listed", said.getvalue())

    def test_the_graphviz_package_is_unpacked_to_the_three_files_it_needs(self):
        archive = self.root / "wg.tgz"
        tarball(archive, FAKE_PACKAGE)
        target = self.root / "out" / "1.0"
        pdfmd.unpack_graphviz(archive, target)
        self.assertEqual(sorted(str(path.relative_to(target)) for path in target.rglob("*") if path.is_file()),
                         sorted([str(Path("dist/index.js")), "LICENSE", "package.json"]))
        broken = self.root / "broken.tgz"
        tarball(broken, {"package/LICENSE": b"x"})
        with self.assertRaises(OSError):
            pdfmd.unpack_graphviz(broken, self.root / "out2")
        self.assertFalse((self.root / "out2").exists())

    @unittest.skipIf(sys.platform == "win32" or NODE is None, "needs node and a POSIX shell")
    def test_the_launchers_run_the_script_with_node_and_graphviz_is_installed_end_to_end(self):
        import pdfmd_lua
        archive = self.root / "wg.tgz"
        tarball(archive, FAKE_PACKAGE)
        seen = {}

        def download(url, destination, sha256):
            seen["sha256"] = sha256
            shutil.copyfile(archive, destination)

        with unittest.mock.patch.object(pdfmd, "download_file", download), \
                unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as shown:
            self.assertTrue(pdfmd.install_extra("diagram:dot"), shown.getvalue())
        self.assertEqual(seen["sha256"], pdfmd.GRAPHVIZ_SHA256)
        tools = pdfmd.tools_directory()
        self.assertEqual(sorted(path.name for path in tools.iterdir()), sorted(pdfmd.GRAPHVIZ_COMMANDS))
        for name in pdfmd.GRAPHVIZ_COMMANDS:
            self.assertTrue(os.access(tools / name, os.X_OK), name)
        ran = subprocess.run([str(tools / "neato"), "-Tsvg"], input="graph { a -- b }", capture_output=True, text=True,
                             env={**os.environ, "PATH": os.pathsep.join([str(Path(NODE).parent), "/usr/bin", "/bin"])})
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertIn("data-engine='neato' data-format='svg'", ran.stdout)
        in_file = self.root / "g.dot"
        in_file.write_text("digraph { a -> b }", encoding="utf-8")
        out_file = self.root / "g.svg"
        subprocess.run([str(tools / "dot"), "-Tsvg", "-o", str(out_file), str(in_file)], check=True,
                       env={**os.environ, "PATH": os.pathsep.join([str(Path(NODE).parent), "/usr/bin", "/bin"])})
        self.assertIn("data-engine='dot'", out_file.read_text(encoding="utf-8"))
        # the copy of the script lives with the package, so a moved or upgraded pdfmd does not break the launchers
        self.assertTrue((tools.parent / "graphviz" / pdfmd.GRAPHVIZ_VERSION / "graphviz.cjs").is_file())
        self.assertEqual((tools.parent / "graphviz" / pdfmd.GRAPHVIZ_VERSION / "graphviz.cjs").read_bytes(),
                         (pdfmd_lua.FILTERS / "graphviz.cjs").read_bytes())


@unittest.skipIf(NODE is None, "needs node")
class Runner(unittest.TestCase):
    """The parts of pdfmd_lua/graphviz.cjs that do not need the WebAssembly package."""

    def run_script(self, *arguments: str, stdin: str = "") -> subprocess.CompletedProcess:
        import pdfmd_lua
        return subprocess.run([NODE, str(pdfmd_lua.FILTERS / "graphviz.cjs"), *arguments], input=stdin,
                              capture_output=True, text=True, timeout=60)

    def test_a_pdf_or_png_is_refused_with_the_reason(self):
        for kind in ("-Tpdf", "-Tpng"):
            done = self.run_script("--lib", "nowhere", kind)
            self.assertEqual(done.returncode, 1)
            self.assertIn("needs Graphviz with Cairo", done.stderr)

    def test_an_unknown_engine_or_option_is_refused(self):
        self.assertEqual(self.run_script("--lib", "x", "--engine", "rm").returncode, 1)
        self.assertEqual(self.run_script("--lib", "x", "--bogus").returncode, 1)
        self.assertEqual(self.run_script("-Tsvg").returncode, 1)               # no --lib
        self.assertIn("graphviz", self.run_script("-V").stdout)


if __name__ == "__main__":
    unittest.main()
