"""v3.32.7: `pdfmd --install kit:SOURCE` (pdfmd_kits/install.py): any repository, kits at its root or in child folders.

The module is pure (the downloader is handed in), so these tests build repositories on disk, a tarball like GitHub's, hostile
tarballs, and a real git repository; nothing touches the network."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path, PureWindowsPath

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

from pdfmd_kits import install as kits_install  # noqa: E402
from pdfmd_kits.install import InstallError, parse_source  # noqa: E402

MB = 1048576


def write(path: Path, text: str = "x\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def kit(folder: Path, name: str, extra: str = "", version: str = "1.0.0") -> Path:
    write(folder / f"{name}.kit", f"kit-format: 1\nname: {name}\nversion: {version}\nlua: [{name}.lua]\n{extra}")
    write(folder / f"{name}.lua", "return {}\n")
    write(folder / "metadata.yaml", "csl: x.csl\n")
    return folder


def tarball(repository: Path, top: str, target: Path) -> Path:
    with tarfile.open(target, "w:gz") as bundle:
        for path in sorted(repository.rglob("*")):
            bundle.add(path, arcname=f"{top}/{path.relative_to(repository).as_posix()}", recursive=False)
    return target


class Parse(unittest.TestCase):
    def test_forms(self):
        cases = {
            "owner/repo": ("github", "owner/repo", "", ""),
            "owner/repo@feature/x": ("github", "owner/repo", "feature/x", ""),
            "https://user@host/g/r.git@feature/x": ("git", "https://user@host/g/r.git", "feature/x", ""),
            "ssh://git@host/g/r.git": ("git", "ssh://git@host/g/r.git", "", ""),
            "git@host:g/r.git@feature/x": ("git", "git@host:g/r.git", "feature/x", ""),
            "owner/repo@v1.2": ("github", "owner/repo", "v1.2", ""),
            "owner/repo#apa7": ("github", "owner/repo", "", "apa7"),
            "owner/repo@abc123#apa7": ("github", "owner/repo", "abc123", "apa7"),
            "https://github.com/owner/repo": ("github", "owner/repo", "", ""),
            "https://github.com/owner/repo.git@v2": ("github", "owner/repo", "v2", ""),
            "https://github.com/owner/repo/tree/dev": ("github", "owner/repo", "dev", ""),
            "https://gitlab.com/g/r.git": ("git", "https://gitlab.com/g/r.git", "", ""),
            "https://gitlab.com/g/r.git@v3#x": ("git", "https://gitlab.com/g/r.git", "v3", "x"),
            "git@github.com:owner/repo.git": ("git", "git@github.com:owner/repo.git", "", ""),
            "git@github.com:owner/repo.git@v1": ("git", "git@github.com:owner/repo.git", "v1", ""),
            "ssh://git@host/x/y.git": ("git", "ssh://git@host/x/y.git", "", ""),
            "~/kits": ("folder", "~/kits", "", ""),
            "./here#apa7": ("folder", "./here", "", "apa7"),
            "/abs/path": ("folder", "/abs/path", "", ""),
            "file:///abs/path": ("git", "file:///abs/path", "", ""),
            "file:///abs/path@v1": ("git", "file:///abs/path", "v1", ""),
            "apa7": ("name", "apa7", "", ""),
        }
        for text, (kind, location, ref, name) in cases.items():
            with self.subTest(text):
                source = parse_source(text)
                self.assertEqual((source.kind, source.location, source.ref, source.name), (kind, location, ref, name))

    def test_refused(self):
        for text in ("", "   ", "http://host/x.git", "git://host/x.git", "owner/repo@", "owner/repo#", "./x@v1", "apa7@v1",
                     "a/b/c", "name@feature/x"):
            with self.subTest(text), self.assertRaises(InstallError):
                parse_source(text)


class Base(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.tmp = Path(self.temporary.name).resolve()
        self.kits_dir = self.tmp / "config" / "kits"
        self.messages: list[str] = []

    def say(self, text):
        self.messages.append(text)

    def run_install(self, text: str, repository: Path | None = None, top: str | None = None, **options):
        """Install from a source whose download is a tarball of ``repository`` (github) or from the source as given."""
        source = parse_source(text)
        kwargs = dict(depth=3, max_bytes=50 * MB, max_files=5000, say=self.say, workdir=self.tmp)
        kwargs.update(options)
        if repository is not None:
            archive = tarball(repository, top or "repo-" + "a" * 40, self.tmp / "serve.tar.gz")
            self.downloaded: list[str] = []

            def download(url, destination, sha256):
                self.downloaded.append(url)
                shutil.copy(archive, destination)
            kwargs["download"] = download
        else:
            kwargs["download"] = lambda *a: self.fail("nothing should be downloaded")
        return kits_install.install(source, self.kits_dir, **kwargs)


class Layouts(Base):
    def test_a_kit_at_the_root_is_one_kit(self):                       # the nulabreport shape
        repo = kit(self.tmp / "nulab", "nulabreport")
        write(repo / "docs" / "other.kit", "kit-format: 1\nname: not-this\n")     # below a kit: belongs to it
        write(repo / "templates" / "x.md")
        done = self.run_install("owner/nulab", repo)
        self.assertEqual([item.name for item in done], ["nulabreport"])
        self.assertTrue((self.kits_dir / "nulabreport" / "nulabreport.kit").is_file())
        self.assertTrue((self.kits_dir / "nulabreport" / "docs" / "other.kit").is_file())    # carried whole
        self.assertFalse((self.kits_dir / "not-this").exists())
        self.assertEqual(self.downloaded, ["https://github.com/owner/nulab/archive/HEAD.tar.gz"])

    def test_kits_in_child_folders(self):                                # the pdfmd-kits shape
        repo = self.tmp / "collection"
        kit(repo / "apa7", "apa7")
        kit(repo / "achemso", "achemso")
        write(repo / "README.md")
        write(repo / "scripts" / "check.sh")
        write(repo / ".hidden" / "ghost" / "ghost.kit", "kit-format: 1\nname: ghost\n")
        kit(repo / "deep" / "er" / "still" / "toodeep", "toodeep")      # four levels down: out of reach at depth 3
        done = self.run_install("owner/collection", repo)
        self.assertEqual(sorted(item.name for item in done), ["achemso", "apa7"])
        self.assertFalse((self.kits_dir / "ghost").exists())
        self.assertFalse((self.kits_dir / "toodeep").exists())

    def test_depth_is_a_setting(self):
        repo = self.tmp / "collection"
        kit(repo / "deep" / "er" / "still" / "toodeep", "toodeep")
        with self.assertRaises(InstallError):
            self.run_install("owner/collection", repo)
        done = self.run_install("owner/collection", repo, depth=4)
        self.assertEqual([item.name for item in done], ["toodeep"])

    def test_a_name_picks_one_kit(self):
        repo = self.tmp / "collection"
        kit(repo / "apa7", "apa7")
        kit(repo / "achemso", "achemso")
        done = self.run_install("owner/collection#apa7", repo)
        self.assertEqual([item.name for item in done], ["apa7"])
        self.assertFalse((self.kits_dir / "achemso").exists())
        with self.assertRaises(InstallError) as caught:
            self.run_install("owner/collection#nothing", repo)
        self.assertIn("nothing", str(caught.exception))

    def test_no_kit_is_an_error_naming_where_it_looked(self):
        repo = self.tmp / "plain"
        write(repo / "README.md")
        with self.assertRaises(InstallError) as caught:
            self.run_install("owner/plain", repo)
        self.assertIn("no kit found", str(caught.exception))

    def test_an_invalid_kit_is_skipped_and_the_valid_one_installed(self):
        repo = self.tmp / "collection"
        kit(repo / "good", "good")
        write(repo / "bad" / "bad.kit", "kit-format: 1\nname: bad\nlua: [missing.lua]\n")
        done = self.run_install("owner/collection", repo)
        self.assertEqual([item.name for item in done], ["good"])
        self.assertTrue(any("skipped" in message and "bad" in message for message in self.messages))
        repo2 = self.tmp / "only-bad"
        write(repo2 / "bad" / "bad.kit", "kit-format: 1\nname: bad\nlua: [missing.lua]\n")
        with self.assertRaises(InstallError):
            self.run_install("owner/only-bad", repo2)

    def test_the_commit_comes_from_the_tarballs_folder(self):
        repo = kit(self.tmp / "r", "one")
        done = self.run_install("owner/r@v1", repo, top="r-" + "b" * 40)
        self.assertEqual(done[0].commit, "b" * 40)
        self.assertEqual(done[0].ref, "v1")
        self.assertEqual(self.downloaded, ["https://github.com/owner/r/archive/v1.tar.gz"])
        record = json.loads((self.kits_dir / "one" / ".pdfmd-install.json").read_text())
        self.assertEqual((record["source"], record["ref"], record["commit"], record["path-in-repository"]),
                         ("owner/r", "v1", "b" * 40, ""))
        self.assertEqual(len(record["archive-sha256"]), 64)


class Records(Base):
    def test_update_replaces_what_it_installed(self):
        repo = kit(self.tmp / "r", "one", version="1.0.0")
        self.run_install("owner/r", repo)
        write(self.kits_dir / "one" / "stale.txt")
        repo = kit(self.tmp / "r2", "one", version="2.0.0")
        done = self.run_install("owner/r", repo)
        self.assertTrue(done[0].replaced)
        self.assertEqual(done[0].version, "2.0.0")
        self.assertFalse((self.kits_dir / "one" / "stale.txt").exists())
        self.assertEqual([p.name for p in self.kits_dir.iterdir()], ["one"])      # no .new / .old left behind

    def test_a_kit_the_user_put_there_is_never_replaced(self):
        write(self.kits_dir / "one" / "one.kit", "kit-format: 1\nname: one\n")
        repo = kit(self.tmp / "r", "one")
        with self.assertRaises(InstallError) as caught:
            self.run_install("owner/r", repo, assume_yes=True)
        self.assertIn("not installed by pdfmd", str(caught.exception))
        self.assertTrue((self.kits_dir / "one" / "one.kit").is_file())

    def test_another_source_needs_yes(self):
        self.run_install("owner/r", kit(self.tmp / "r", "one"))
        other = kit(self.tmp / "r2", "one")
        with self.assertRaises(InstallError) as caught:
            self.run_install("someone/else", other)
        self.assertIn("--yes", str(caught.exception))
        self.run_install("someone/else", other, assume_yes=True)
        record = json.loads((self.kits_dir / "one" / ".pdfmd-install.json").read_text())
        self.assertEqual(record["source"], "someone/else")

    def test_uninstall_removes_only_installed_kits(self):
        self.run_install("owner/r", kit(self.tmp / "r", "one"))
        write(self.kits_dir / "mine" / "mine.kit", "kit-format: 1\nname: mine\n")
        self.assertEqual([record["kit"] for _, record in kits_install.installed_kits(self.kits_dir)], ["one"])
        with self.assertRaises(InstallError):
            kits_install.uninstall("mine", self.kits_dir)
        self.assertTrue((self.kits_dir / "mine").is_dir())
        kits_install.uninstall("One", self.kits_dir)                      # a name, compared like kit names
        self.assertFalse((self.kits_dir / "one").exists())
        self.assertTrue((self.kits_dir / "mine").is_dir())


class Safety(Base):
    def archive(self, members) -> Path:
        path = self.tmp / "bad.tar.gz"
        with tarfile.open(path, "w:gz") as bundle:
            for info, data in members:
                bundle.addfile(info, io.BytesIO(data) if data is not None else None)
        return path

    def info(self, name, data=b"x", kind=tarfile.REGTYPE, link=""):
        item = tarfile.TarInfo(name)
        item.type, item.size, item.linkname = kind, len(data) if kind == tarfile.REGTYPE else 0, link
        return item

    def test_a_name_that_leaves_the_folder_is_refused(self):
        for name in ("repo/../../evil", "/etc/evil", "../evil"):
            with self.subTest(name), self.assertRaises(InstallError):
                kits_install.safe_extract(self.archive([(self.info(name), b"x")]), self.tmp / "out", MB, 100)
        self.assertFalse((self.tmp / "evil").exists())

    def test_windows_member_names_are_refused_on_every_host(self):
        names = (r"repo/..\..\escape.txt", "C:/escape.txt", "C:escape.txt",
                 r"\escape.txt", r"\\server\share\escape.txt", "repo/C:/escape.txt",
                 "repo/C:escape.txt", "repo/../escape.txt")
        for name in names:
            with self.subTest(name=name):
                self.assertTrue(PureWindowsPath(name).drive or PureWindowsPath(name).root
                                or ".." in PureWindowsPath(name).parts or "C:" in name)
                with self.assertRaisesRegex(InstallError, "refused"):
                    kits_install.safe_extract(self.archive([(self.info(name), b"x")]), self.tmp / "out", MB, 100)

    def test_extraction_refuses_a_pre_existing_symlink_escape(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        victim = write(outside / "keep.txt", "keep\n")
        destination = self.tmp / "out"
        destination.mkdir()
        (destination / "repo").symlink_to(outside, target_is_directory=True)
        archive = self.archive([(self.info("repo/keep.txt"), b"lost")])
        with self.assertRaisesRegex(InstallError, "refused"):
            kits_install.safe_extract(archive, destination, MB, 100)
        self.assertEqual(victim.read_text(), "keep\n")

    def test_cli_refuses_windows_archive_names_without_network(self):
        archive = self.archive([(self.info(r"repo/..\..\escape.txt"), b"lost")])
        hook = self.tmp / "hook"
        hook.mkdir()
        (hook / "sitecustomize.py").write_text(
            "import os, shutil, pdfmd\nfrom pathlib import Path\n"
            "pdfmd.kits_install_directory = lambda: Path(os.environ['XDG_CONFIG_HOME']) / 'kits'\n"
            "pdfmd.download_file = lambda url, destination, sha256: "
            "shutil.copyfile(os.environ['PDFMD_TEST_ARCHIVE'], destination)\n", encoding="utf-8")
        env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
               "PDFMD_TEST_ARCHIVE": str(archive), "PYTHONPATH": os.pathsep.join((str(hook), str(ROOT))),
               **{key: str(self.tmp / key) for key in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME")}}
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--install", "kit:owner/repo", "--yes"],
                              cwd=self.tmp, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("refused", done.stdout + done.stderr)
        self.assertIn("escape.txt", done.stdout + done.stderr)

    def test_links_and_special_files_are_not_kept(self):
        archive = self.archive([
            (self.info("repo/ok.txt"), b"ok"),
            (self.info("repo/link", kind=tarfile.SYMTYPE, link="/etc/passwd"), None),
            (self.info("repo/hard", kind=tarfile.LNKTYPE, link="repo/ok.txt"), None),
            (self.info("repo/fifo", kind=tarfile.FIFOTYPE), None)])
        root = kits_install.safe_extract(archive, self.tmp / "out", MB, 100)
        self.assertEqual(sorted(p.name for p in root.iterdir()), ["ok.txt"])

    def test_caps(self):
        archive = self.archive([(self.info(f"repo/f{i}"), b"x") for i in range(5)])
        with self.assertRaises(InstallError) as caught:
            kits_install.safe_extract(archive, self.tmp / "out1", MB, 4)
        self.assertIn("kit-install-max-files", str(caught.exception))
        big = self.archive([(self.info("repo/big", b"x" * (2 * MB)), b"x" * (2 * MB))])
        with self.assertRaises(InstallError) as caught:
            kits_install.safe_extract(big, self.tmp / "out2", MB, 100)
        self.assertIn("kit-install-max-mb", str(caught.exception))

    def test_nothing_is_written_outside_on_a_refused_archive_through_install(self):
        repo = kit(self.tmp / "r", "one")
        bad = self.archive([(self.info("repo/../../escape"), b"x")])

        def download(url, destination, sha256):
            shutil.copy(bad, destination)
        with self.assertRaises(InstallError):
            kits_install.install(parse_source("owner/r"), self.kits_dir, depth=3, max_bytes=MB, max_files=10, download=download,
                                 say=self.say, workdir=self.tmp)
        self.assertFalse(self.kits_dir.exists() and any(self.kits_dir.iterdir()))
        self.assertTrue(repo.exists())

    def test_a_folder_source_skips_links_and_git(self):
        repo = kit(self.tmp / "folder", "one")
        write(repo / ".git" / "config", "[core]\n")
        (repo / "link").symlink_to(self.tmp)
        self.run_install(str(repo))
        self.assertTrue((self.kits_dir / "one" / "one.kit").is_file())
        self.assertFalse((self.kits_dir / "one" / ".git").exists())
        self.assertFalse((self.kits_dir / "one" / "link").exists())


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class Git(Base):
    def make(self) -> Path:
        repo = self.tmp / "gitrepo"
        kit(repo / "apa7", "apa7", version="1.0.0")
        run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)   # noqa: E731
        run("init", "-q", "-b", "main")
        run("-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
        run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "one")
        run("-c", "user.name=t", "-c", "user.email=t@t", "tag", "v1")
        write(repo / "apa7" / "apa7.kit", "kit-format: 1\nname: apa7\nversion: 2.0.0\nlua: [apa7.lua]\n")
        run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-am", "two")
        return repo

    def test_a_git_url_and_a_ref(self):
        repo = self.make()
        url = f"file://{repo}"
        done = self.run_install(f"{url}@v1")
        self.assertEqual(done[0].version, "1.0.0")
        self.assertEqual(len(done[0].commit), 40)
        done = self.run_install(url)
        self.assertEqual(done[0].version, "2.0.0")
        self.assertTrue(done[0].replaced)
        record = json.loads((self.kits_dir / "apa7" / ".pdfmd-install.json").read_text())
        self.assertEqual(record["path-in-repository"], "apa7")


if __name__ == "__main__":
    unittest.main()
