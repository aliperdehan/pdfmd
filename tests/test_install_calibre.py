"""v3.29.3: `pdfmd --install calibre`. Nothing here downloads Calibre: the release listing is a fake, the download a stand-in that
copies a tiny archive (a .txz on Linux, a disk image on macOS) holding a stand-in `ebook-convert`."""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

SCRIPT = "#!/bin/sh\necho 'ebook-convert (calibre 9.99.0)'\n"


def release(*names: str, digest: bool = True) -> dict:
    return {"assets": [{"name": name, "browser_download_url": f"https://example.invalid/{name}",
                        **({"digest": "sha256:" + "ab" * 32} if digest else {})} for name in names]}


class Assets(unittest.TestCase):
    def test_the_file_for_each_machine(self):
        cases = {("Darwin", "arm64"): "calibre-9.16.0.dmg", ("Darwin", "x86_64"): "calibre-9.16.0.dmg",
                 ("Linux", "x86_64"): "calibre-9.16.0-x86_64.txz", ("Linux", "aarch64"): "calibre-9.16.0-arm64.txz",
                 ("Linux", "arm64"): "calibre-9.16.0-arm64.txz"}
        names = ["calibre-64bit-9.16.0.msi", "calibre-9.16.0-arm64.txz", "calibre-9.16.0-x86_64.txz", "calibre-9.16.0.dmg",
                 "calibre-9.16.0.tar.xz", "calibre-portable-installer-9.16.0.exe"]
        for (system, machine), expected in cases.items():
            pattern = pdfmd.calibre_asset_pattern(system, machine)
            found = pdfmd.calibre_release_asset(pattern, release(*names))
            self.assertEqual(found[0], expected, (system, machine))
            self.assertEqual(found[2], "ab" * 32)

    def test_windows_and_other_machines_have_none(self):
        self.assertIsNone(pdfmd.calibre_asset_pattern("Windows", "AMD64"))
        self.assertIsNone(pdfmd.calibre_asset_pattern("Linux", "riscv64"))

    def test_a_file_with_no_digest_is_not_offered(self):
        pattern = pdfmd.calibre_asset_pattern("Linux", "x86_64")
        self.assertIsNone(pdfmd.calibre_release_asset(pattern, release("calibre-9.16.0-x86_64.txz", digest=False)))
        self.assertIsNone(pdfmd.calibre_release_asset(pattern, release("calibre-9.16.0.dmg")))


class Unpack(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-calibre-install-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def archive(self, members: dict[str, bytes], links: dict[str, str] | None = None) -> Path:
        path = self.directory / "c.txz"
        with tarfile.open(path, "w:xz") as bundle:
            for name, data in members.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o755
                bundle.addfile(info, io.BytesIO(data))
            for name, target in (links or {}).items():
                info = tarfile.TarInfo(name)
                info.type = tarfile.SYMTYPE
                info.linkname = target
                bundle.addfile(info)
        return path

    def test_a_good_archive_is_unpacked(self):
        target = self.directory / "out"
        pdfmd.safe_unpack_tar(self.archive({"ebook-convert": b"x", "lib/a.so": b"y"}, {"lib/b.so": "a.so"}), target)
        self.assertEqual((target / "ebook-convert").read_bytes(), b"x")
        self.assertTrue((target / "lib" / "b.so").is_symlink())

    def test_a_member_outside_the_folder_is_refused(self):
        for bad in ("../escape", "/abs/path"):
            target = self.directory / "out2"
            with self.assertRaises(OSError):
                pdfmd.safe_unpack_tar(self.archive({bad: b"x"}), target)
            self.assertFalse((self.directory / "escape").exists())

    def test_a_link_out_of_the_folder_is_refused(self):
        with self.assertRaises(OSError):
            pdfmd.safe_unpack_tar(self.archive({"a": b"x"}, {"evil": "../../etc/passwd"}), self.directory / "out3")


@unittest.skipIf(sys.platform == "win32", "Windows is a package manager's job")
class Install(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="pdfmd-calibre-install-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        data = self.directory / "data"
        data.mkdir()
        patch = mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(data), "LOCALAPPDATA": str(data)})
        patch.start()
        self.addCleanup(patch.stop)
        self.apps = self.directory / "Applications"
        self.fetched: list[tuple[str, str]] = []

    def find(self) -> str | None:
        """Calibre as this test's folders have it (the machine's own copy must not count)."""
        if os.environ.get("PDFMD_CALIBRE"):
            return os.environ["PDFMD_CALIBRE"]
        places = [folder / "ebook-convert" for folder in pdfmd.calibre_own_folders()]
        places.append(self.apps / "calibre.app" / "Contents" / "MacOS" / "ebook-convert")
        return next((str(place) for place in places if place.is_file()), None)

    def run_install(self, **kwargs) -> tuple[bool, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            done = pdfmd.install_calibre(interactive=False, applications=self.apps, find=self.find, **kwargs)
        return done, out.getvalue(), err.getvalue()

    def fetch_with(self, source: Path):
        def fetch(url, destination, sha256):
            self.fetched.append((url, sha256))
            shutil.copyfile(source, destination)
        return fetch

    @unittest.skipUnless(sys.platform.startswith("linux"), "the .txz route is Linux's")
    def test_linux_unpacks_the_archive_and_finds_ebook_convert(self):
        archive = self.directory / "c.txz"
        with tarfile.open(archive, "w:xz") as bundle:
            data = SCRIPT.encode()
            info = tarfile.TarInfo("ebook-convert")
            info.size = len(data)
            info.mode = 0o755
            bundle.addfile(info, io.BytesIO(data))
        pattern_machine = pdfmd.platform.machine().lower()
        name = "calibre-9.99.0-" + ("arm64" if pattern_machine in ("aarch64", "arm64") else "x86_64") + ".txz"
        done, out, err = self.run_install(fetch=self.fetch_with(archive), release=release(name))
        self.assertTrue(done, out + err)
        self.assertIn("SHA-256 verified (abababababab", out)
        self.assertIn("ebook-convert (calibre 9.99.0)", out)
        self.assertEqual(self.fetched, [(f"https://example.invalid/{name}", "ab" * 32)])
        self.assertTrue(self.find().endswith(os.path.join("calibre", "9.99.0", "ebook-convert")), self.find())
        self.assertEqual([folder.name for folder in pdfmd.calibre_own_folders()], ["9.99.0"])

    @unittest.skipUnless(sys.platform == "darwin" and shutil.which("hdiutil"), "the disk-image route is macOS's")
    def test_macos_copies_the_app_and_detaches_the_image(self):
        source = self.directory / "image-src"
        binary = source / "calibre.app" / "Contents" / "MacOS" / "ebook-convert"
        binary.parent.mkdir(parents=True)
        binary.write_text(SCRIPT, encoding="utf-8")
        binary.chmod(0o755)
        image = self.directory / "calibre.dmg"
        made = subprocess.run(["hdiutil", "create", "-srcfolder", str(source), "-format", "UDZO", "-ov", str(image)],
                              capture_output=True, text=True)
        self.assertEqual(made.returncode, 0, made.stderr)
        before = subprocess.run(["hdiutil", "info"], capture_output=True, text=True).stdout.count("pdfmd-calibre-dmg")
        done, out, err = self.run_install(fetch=self.fetch_with(image), release=release("calibre-9.99.0.dmg"))
        self.assertTrue(done, out + err)
        self.assertTrue((self.apps / "calibre.app" / "Contents" / "MacOS" / "ebook-convert").is_file())
        after = subprocess.run(["hdiutil", "info"], capture_output=True, text=True).stdout.count("pdfmd-calibre-dmg")
        self.assertEqual(before, after)                                              # the image is detached again

    def test_no_digest_no_download(self):
        pattern_name = "calibre-9.99.0.dmg" if sys.platform == "darwin" else "calibre-9.99.0-x86_64.txz"
        done, out, err = self.run_install(fetch=self.fetch_with(self.directory), release=release(pattern_name, digest=False))
        self.assertFalse(done)
        self.assertEqual(self.fetched, [])
        self.assertIn("SHA-256", err)

    def test_a_download_that_fails_the_check_installs_nothing(self):
        def failing(url, destination, sha256):
            raise OSError(f"SHA-256 mismatch for {url}")
        name = "calibre-9.99.0.dmg" if sys.platform == "darwin" else (
            "calibre-9.99.0-arm64.txz" if pdfmd.platform.machine().lower() in ("aarch64", "arm64") else "calibre-9.99.0-x86_64.txz")
        done, out, err = self.run_install(fetch=failing, release=release(name))
        self.assertFalse(done)
        self.assertIn("SHA-256 mismatch", err)
        self.assertFalse((self.directory / "data" / "pdfmd" / "calibre").exists())
        self.assertFalse((self.apps / "calibre.app").exists())

    def test_an_installed_calibre_is_left_alone(self):
        stub = self.directory / "ebook-convert"
        stub.write_text(SCRIPT, encoding="utf-8")
        with mock.patch.dict(os.environ, {"PDFMD_CALIBRE": str(stub)}):
            done, out, err = self.run_install(fetch=self.fetch_with(self.directory))
        self.assertTrue(done)
        self.assertIn("already installed", out)
        self.assertEqual(self.fetched, [])


class OwnFolder(unittest.TestCase):
    def test_the_newest_version_comes_first_and_resolve_finds_it(self):
        with tempfile.TemporaryDirectory(prefix="pdfmd-calibre-own-") as data:
            for version in ("9.2.0", "9.16.0", "8.20.1"):
                folder = Path(data) / "pdfmd" / "calibre" / version
                folder.mkdir(parents=True)
                (folder / "ebook-convert").write_text(SCRIPT, encoding="utf-8")
                (folder / "ebook-convert").chmod(0o755)
            with mock.patch.dict(os.environ, {"XDG_DATA_HOME": data, "LOCALAPPDATA": data}):
                os.environ.pop("PDFMD_CALIBRE", None)
                self.assertEqual([folder.name for folder in pdfmd.calibre_own_folders()], ["9.16.0", "9.2.0", "8.20.1"])
                with mock.patch.object(pdfmd, "which", lambda name, *a, **k: None):
                    found = pdfmd.resolve_calibre()
                self.assertTrue(found and "9.16.0" in found or sys.platform != "linux", found)


class Manager(unittest.TestCase):
    def test_the_package_manager_is_a_command_without_sudo(self):
        for system, tools, expected in (("darwin", {"brew"}, ["brew", "install", "--cask", "calibre"]),
                                        ("win32", {"winget"}, ["winget", "install", "--id", "calibre.calibre", "-e"]),
                                        ("linux", {"apt"}, None), ("darwin", set(), None)):
            with mock.patch.object(pdfmd.sys, "platform", system), \
                    mock.patch.object(pdfmd, "which", lambda name, *a, tools=tools, **k: name if name in tools else None):
                self.assertEqual(pdfmd.calibre_package_manager(), expected, system)

    def test_it_is_a_kind_of_install(self):
        self.assertIn("calibre", pdfmd.INSTALL_KINDS)
        self.assertEqual(pdfmd.install_kind("calibre"), "calibre")
        with self.assertRaises(Exception):
            pdfmd.install_kind("calibre:x")


if __name__ == "__main__":
    unittest.main()
