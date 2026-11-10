"""The cache by part (v3.33.74): `pdfmd --cache-info`, `pdfmd --clear-cache builds|documents|stale|all` and the `--doctor` NOTE
over `cache.max-mb` (pdfmd_cache.manage). Every case builds a fake cache in a folder of its own (XDG_CACHE_HOME)."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)
from cache_support import cache_env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["PDFMD_CONFIG"] = ""
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="pdfmd-test-config-")

import pdfmd  # noqa: E402

manage = pdfmd.load_package("pdfmd_cache.manage")


class FakeCache(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.top = Path(folder.name).resolve()
        self.env = cache_env(self.top / "cache")
        patcher = mock.patch.dict(os.environ, self.env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = self.top / "cache" / "pdfmd"
        self.docs = self.top / "docs"
        self.docs.mkdir()
        self.doc = self.docs / "doc.md"
        self.doc.write_text("# A\n\nx\n", encoding="utf-8")
        self.outside = self.top / "outside"
        self.outside.mkdir()
        (self.outside / "keep.txt").write_text("k" * 3000, encoding="utf-8")
        gone = str(self.top / "moved-away" / "gone.md")
        self.file("builds/doc-aaaaaaaa/20261110-120000-ok.log", f"pdfmd build record\ndocument:  {self.doc}\n" + "y" * 1000)
        self.file("builds/gone-bbbbbbbb/20261110-120000-ok.log", f"pdfmd build record\ndocument:  {gone}\n" + "y" * 2000)
        (self.root / "builds" / "none-cccccccc").mkdir()
        self.file("0123456789-doc/doc.aux", "a" * 2000)
        self.file("0123456789-doc/.pdfmd-source.json", json.dumps({"path": str(self.doc)}))
        self.file("abcdef0123-gone/gone.aux", "a" * 5000)
        self.file("abcdef0123-gone/.pdfmd-source.json", json.dumps({"path": gone}))
        os.symlink(self.outside, self.root / "abcdef0123-gone" / "out", target_is_directory=True)        # a link inside a stale cache
        self.file("fedcba9876-old/old.aux", "a" * 1000)                          # records no document
        self.file("tex/a.tex", "t" * 10000)
        self.file("office/b.docx", "o" * 4000)
        self.file("CACHEDIR.TAG", "Signature\n")

    def file(self, name: str, text: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_manage(self, function, *arguments) -> tuple[object, str]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            result = function(*arguments)
        return result, out.getvalue()

    def run_pdfmd(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.docs, stdin=subprocess.DEVNULL,
                              env={**os.environ, **self.env, "PDFMD_NO_PROMPT": "1", "PDFMD_CONFIG": ""})


class Info(FakeCache):
    def test_each_part_its_size_and_what_is_stale(self):
        status, out = self.run_manage(manage.cache_info, self.docs)
        self.assertEqual(status, 0)
        lines = {line.split()[0]: line for line in out.splitlines() if line.startswith("  ")}
        self.assertRegex(lines["<hash>-<name>/"], r"3 document caches, 1 stale \(5\.\d KB\), 1 unrecorded$")    # with the paths
        self.assertRegex(lines["builds/"], r"3 documents' build records, 1 stale \(2\.\d KB\), 1 unrecorded$")
        self.assertIn("10.0 KB  shared by every document", lines["tex/"])
        self.assertIn("4.0 KB  shared by every document", lines["office/"])
        self.assertIn("CACHEDIR.TAG", lines["files"])
        self.assertIn("Stale: 2 folders whose document is gone", out)
        self.assertNotIn("keep.txt", out)
        self.assertLess(manage.tree_size(self.root / "abcdef0123-gone"), 5300)    # the link is not followed

    def test_the_document_each_folder_records(self):
        found = manage.survey(self.root)
        self.assertEqual({folder.name: document for folder, _, document in found["documents"]},
                         {"0123456789-doc": self.doc, "abcdef0123-gone": self.top / "moved-away" / "gone.md",
                          "fedcba9876-old": None})
        self.assertEqual({folder.name: document for folder, _, document in found["builds"]},
                         {"doc-aaaaaaaa": self.doc, "gone-bbbbbbbb": self.top / "moved-away" / "gone.md",
                          "none-cccccccc": None})

    def test_no_cache_yet(self):
        with mock.patch.dict(os.environ, cache_env(self.top / "empty")):
            status, out = self.run_manage(manage.cache_info, self.docs)
        self.assertEqual(status, 0)
        self.assertIn("does not exist", out)

    def test_through_pdfmd(self):
        done = self.run_pdfmd("--cache-info")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("pdfmd's cache:", done.stdout)
        self.assertIn("pdfmd --clear-cache stale", done.stdout)
        refused = self.run_pdfmd("--cache-info", "doc.md")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("--cache-info takes no document", refused.stderr)


class Clear(FakeCache):
    def names(self) -> set[str]:
        return {path.name for path in self.root.iterdir()} if self.root.exists() else set()

    def test_stale_removes_only_what_lost_its_document(self):
        status, out = self.run_manage(manage.clear_cache, "stale", self.docs)
        self.assertEqual(status, 0)
        self.assertFalse((self.root / "abcdef0123-gone").exists())
        self.assertFalse((self.root / "builds" / "gone-bbbbbbbb").exists())
        for kept in ("0123456789-doc", "fedcba9876-old", "builds/doc-aaaaaaaa", "builds/none-cccccccc", "tex"):
            self.assertTrue((self.root / kept).exists(), kept)
        self.assertTrue((self.outside / "keep.txt").exists())                   # the link went, not what it pointed at
        self.assertRegex(out, r"abcdef0123-gone  5\.\d KB\n")
        self.assertRegex(out, r"CLEARED  2 folders, 7\.\d KB\n")
        _, again = self.run_manage(manage.clear_cache, "stale", self.docs)
        self.assertIn("NOTHING  no stale folders", again)

    def test_builds_and_documents(self):
        self.run_manage(manage.clear_cache, "builds", self.docs)
        self.assertNotIn("builds", self.names())
        self.run_manage(manage.clear_cache, "documents", self.docs)
        self.assertEqual(self.names(), {"tex", "office", "CACHEDIR.TAG"})
        self.assertTrue((self.outside / "keep.txt").exists())

    def test_all_and_the_folders_own_cache(self):
        local = self.docs / ".cache" / "pdfmd" / "doc"
        local.mkdir(parents=True)
        (local / "x.aux").write_text("x", encoding="utf-8")
        status, out = self.run_manage(manage.clear_cache, "all", self.docs)
        self.assertEqual(status, 0)
        self.assertFalse(self.root.exists())
        self.assertFalse((self.docs / ".cache" / "pdfmd").exists())
        self.assertTrue((self.outside / "keep.txt").exists())
        self.assertEqual(out.count("CLEARED"), 3)                               # two folders and the total

    def test_a_cache_folder_that_is_a_link_is_not_cleared_by_all(self):
        linked = self.top / "linked"
        linked.mkdir()
        os.symlink(self.root, linked / "pdfmd", target_is_directory=True)
        with mock.patch.dict(os.environ, cache_env(linked)):
            status, out = self.run_manage(manage.clear_cache, "all", self.docs)
        self.assertEqual(status, 1)
        self.assertIn("is a symbolic link", out)
        self.assertTrue((self.root / "tex" / "a.tex").exists())

    def test_nothing_outside_the_cache_is_removed(self):
        _, out = self.run_manage(manage.remove_all, [self.outside], [self.root])
        self.assertIn("SKIPPED", out)
        self.assertTrue((self.outside / "keep.txt").exists())
        _, out = self.run_manage(manage.remove_all, [self.root / ".." / "pdfmd" / ".." / ".." / "outside"], [self.root])
        self.assertIn("SKIPPED", out)
        self.assertTrue((self.outside / "keep.txt").exists())

    def test_a_value_that_is_no_word_is_the_document(self):
        arguments = SimpleNamespace(clear_cache="doc.md", cache_info=False, path=[])
        self.assertIsNone(manage.cache_command(arguments))                      # the bare --clear-cache runs on
        self.assertEqual((arguments.clear_cache, arguments.path), (True, [Path("doc.md")]))
        with self.assertRaises(SystemExit) as caught:
            manage.cache_command(SimpleNamespace(clear_cache="builds", cache_info=False, path=[Path("doc.md")]))
        self.assertIn("takes no document", str(caught.exception))

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc: the bare --clear-cache stops without it, as before")
    def test_a_document_through_pdfmd(self):
        digest = hashlib.sha1(str(self.doc.resolve()).encode("utf-8")).hexdigest()[:10]
        self.file(f"{digest}-doc/doc.aux", "a" * 100)
        done = self.run_pdfmd("--clear-cache", "doc.md")                        # a document, as before: its cache only
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertFalse((self.root / f"{digest}-doc").exists())
        self.assertTrue((self.root / "0123456789-doc").exists())
        self.assertIn(f"{digest}-doc  100 B", done.stdout)

    def test_through_pdfmd(self):
        done = self.run_pdfmd("--clear-cache", "stale")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertFalse((self.root / "abcdef0123-gone").exists())
        done = self.run_pdfmd("--clear-cache=builds")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertFalse((self.root / "builds").exists())
        refused = self.run_pdfmd("--clear-cache", "documents", "doc.md")
        self.assertNotEqual(refused.returncode, 0)
        self.assertTrue((self.root / "0123456789-doc").exists())


class DoctorNote(unittest.TestCase):
    def test_over_the_setting(self):
        with mock.patch.object(pdfmd, "config_options", return_value={}):
            self.assertIsNone(manage.size_note(999_000_000))
            self.assertIn("1.0 GB, more than cache.max-mb (1000 MB)", manage.size_note(1_000_000_001))
        with mock.patch.object(pdfmd, "config_options", return_value={"cache": {"max-mb": 5}}):
            self.assertIn("more than cache.max-mb (5 MB)", manage.size_note(6_000_000))
            self.assertIsNone(manage.size_note(4_000_000))
        with mock.patch.object(pdfmd, "config_options", return_value={"cache": {"max-mb": 0}}):
            self.assertIsNone(manage.size_note(10 ** 12))


if __name__ == "__main__":
    unittest.main()
