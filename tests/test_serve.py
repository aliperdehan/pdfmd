"""`pdfmd --serve` and `pdfmd --api` (entry 3do): the JSON core, the HTTP shell, the command line, and that the shapes are the ones the page's
fixtures show (the page is built against the fixtures, so a drift here breaks the page)."""

from __future__ import annotations

import contextlib
from concurrent.futures import ThreadPoolExecutor
import http.client
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401  (the run's own cache, config and data folders: never the real ones)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))

import pdfmd as _pdfmd  # noqa: E402,F401  (binds the shared excerpt commands)
from pdfmd_serve import API_VERSION, ApiError, Core, Server  # noqa: E402

PANDOC = shutil.which("pandoc")
WEB = ROOT / "lib" / "pdfmd_web"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _kill(pid: int) -> None:
    if os.name == "posix" and _alive(pid):
        import signal
        os.kill(pid, signal.SIGTERM)


def answer_status(connection) -> int:
    """The status of the answer, read to its end: closing a keep-alive connection with the answer unread resets it (Windows
    raises ConnectionResetError in the server's idle handler, which prints a traceback), so every test reads the body."""
    response = connection.getresponse()
    response.read()
    return response.status


def fixtures() -> dict:
    text = (WEB / "fixtures" / "fixtures.js").read_text(encoding="utf-8")
    return json.loads(text.split("window.FIXTURES = ", 1)[1].rstrip().rstrip(";"))


class Folder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "proj"
        self.root.mkdir()
        (self.root / "report.md").write_text("---\ntitle: T\n---\n\n# One\n\ntext\n\n```\n# not a heading\n```\n\n## Two ##\n", encoding="utf-8")
        (self.root / "refs.bib").write_text("@book{a, title={T}}\n", encoding="utf-8")
        (self.root / "sub").mkdir()
        (self.root / "sub" / "n.md").write_text("# N\n", encoding="utf-8")
        (self.root / ".hidden").write_text("x", encoding="utf-8")
        self.core = Core(self.root, pick_main=lambda root: (root / "report.md", "the only one"),
                         discover=lambda root, main: [{"role": "bibliography", "file": "refs.bib"}])

    def get(self, target):
        return self.core.handle("GET", target)


class Handlers(Folder):
    def test_filesystem_failures_are_structured_api_errors(self):
        with mock.patch.object(Path, "read_bytes", side_effect=PermissionError("denied")):
            status, answer = self.get("/api/file?path=report.md")
            self.assertEqual((status, answer["api"], answer["code"]), (403, API_VERSION, "permission"))
            (self.root / "pic.png").touch()
            with self.assertRaises(ApiError) as error:
                self.core.raw({"path": "pic.png"})
            self.assertEqual((error.exception.status, error.exception.code), (403, "permission"))
        with mock.patch.object(self.core, "write_bytes", side_effect=OSError("disk error")):
            status, answer = self.core.handle("POST", "/api/file", {"path": "new.md", "text": "text"})
            self.assertEqual((status, answer["api"], answer["code"]), (500, API_VERSION, "filesystem"))

    def test_project_has_the_shape_of_the_fixture(self):
        status, project = self.get("/api/project")
        self.assertEqual(status, 200)
        self.assertEqual(project["api"], API_VERSION)
        fixture = fixtures()["project"]
        self.assertEqual(set(project) - {"api"}, set(fixture))
        self.assertEqual({type(v) for v in project.values()} - {type(None)}, {type(v) for v in fixture.values()} | {int})
        self.assertEqual(set(project["tree"][0]), set(fixture["tree"][0]))
        self.assertEqual(set(project["discovered"][0]), set(fixture["discovered"][0]))
        self.assertEqual(project["main"], "report.md")
        self.assertEqual([item["name"] for item in project["tree"]], ["refs.bib", "report.md", "sub/n.md"], "hidden files are not listed")

    def test_outline_has_the_shape_of_the_fixture_and_skips_fences_and_front_matter(self):
        status, answer = self.get("/api/outline?path=report.md")
        self.assertEqual(status, 200)
        self.assertEqual(answer["items"], [{"level": 1, "title": "One", "line": 5}, {"level": 2, "title": "Two", "line": 13}])
        self.assertEqual(set(answer["items"][0]), set(fixtures()["outline"]["report.md"][0]))
        self.assertEqual(self.get("/api/outline?path=refs.bib")[1]["items"], [])

    def test_a_file_is_read_and_saved_with_its_mtime(self):
        _, read = self.get("/api/file?path=report.md")
        self.assertIn("# One", read["text"])
        status, saved = self.core.handle("PUT", "/api/file", {"path": "report.md", "text": "# Changed\n", "mtime": read["mtime"]})
        self.assertEqual(status, 200)
        self.assertEqual((self.root / "report.md").read_text(encoding="utf-8"), "# Changed\n")
        self.assertNotEqual(saved["mtime"], read["mtime"])
        # the old mtime now names a file that has changed: nothing is written
        status, refused = self.core.handle("PUT", "/api/file", {"path": "report.md", "text": "lost", "mtime": read["mtime"]})
        self.assertEqual((status, refused["code"]), (409, "conflict"))
        self.assertEqual(refused["mtime"], saved["mtime"])
        self.assertEqual((self.root / "report.md").read_text(encoding="utf-8"), "# Changed\n")
        # no mtime at all is the same as a stale one
        self.assertEqual(self.core.handle("PUT", "/api/file", {"path": "report.md", "text": "x"})[0], 409)

    def test_a_file_replaced_while_it_is_read_is_not_overwritten_by_the_next_save(self):
        # another program replaces the file between the read of its bytes and the version the answer carries (review finding G4.2)
        target = self.root / "report.md"
        old_text = target.read_text(encoding="utf-8")
        real_read_bytes = Path.read_bytes

        def read_then_replaced(path):
            data = real_read_bytes(path)
            if path == target:
                replacement = target.with_name("report.md.new")
                replacement.write_text("# Written by another program\n", encoding="utf-8")
                stamp = target.stat().st_mtime_ns + 5_000_000_000      # a clearly newer mtime, whatever the clock's resolution
                os.utime(replacement, ns=(stamp, stamp))
                os.replace(replacement, target)
            return data

        with mock.patch.object(Path, "read_bytes", read_then_replaced):
            status, read = self.get("/api/file?path=report.md")
        self.assertEqual((status, read["text"]), (200, old_text), "the bytes read are the old file's")
        status, refused = self.core.handle("PUT", "/api/file", {"path": "report.md", "text": "edited old text", "mtime": read["mtime"]})
        self.assertEqual((status, refused.get("code")), (409, "conflict"), "the version must not authorise overwriting the replacement")
        self.assertEqual(target.read_text(encoding="utf-8"), "# Written by another program\n")

    def test_a_save_keeps_the_line_endings_and_the_bom(self):
        (self.root / "win.md").write_bytes(b"\xef\xbb\xbf# A\r\n\r\ntext\r\n")
        _, read = self.get("/api/file?path=win.md")
        self.assertEqual((read["lineEnding"], read["encoding"]), ("crlf", "utf-8-sig"))
        self.assertNotIn("\r", read["text"])
        self.core.handle("PUT", "/api/file", {"path": "win.md", "text": read["text"] + "more\n", "mtime": read["mtime"]})
        self.assertEqual((self.root / "win.md").read_bytes(), b"\xef\xbb\xbf# A\r\n\r\ntext\r\nmore\r\n")

    def test_a_new_file_never_overwrites(self):
        status, made = self.core.handle("POST", "/api/file", {"path": "deep/new.md", "text": "a\nb"})
        self.assertEqual(status, 201)
        self.assertEqual((self.root / "deep" / "new.md").read_text(encoding="utf-8"), "a\nb")
        self.assertEqual(self.core.handle("POST", "/api/file", {"path": "deep/new.md", "text": "x"})[0], 409)
        self.assertEqual((self.root / "deep" / "new.md").read_text(encoding="utf-8"), "a\nb")
        self.assertEqual(self.core.handle("PUT", "/api/file", {"path": "ghost.md", "text": "x", "mtime": "1"})[0], 404)

    def test_nothing_outside_the_folder_is_reachable(self):
        outside = self.root.parent / "secret.md"
        outside.write_text("secret", encoding="utf-8")
        for name in ("../secret.md", str(outside), "sub/../../secret.md", ".git/config"):
            status, answer = self.get("/api/file?path=" + name.replace("&", "%26"))
            self.assertEqual((status, answer.get("code")), (403, "outside"), name)
            self.assertEqual(self.core.handle("PUT", "/api/file", {"path": name, "text": "x", "mtime": "1"})[0], 403, name)
            self.assertEqual(self.core.handle("POST", "/api/file", {"path": name, "text": "x"})[0], 403, name)
        try:
            os.symlink(outside, self.root / "link.md")
        except (OSError, NotImplementedError):
            return                          # no symlinks here (Windows without the right)
        self.assertEqual(self.get("/api/file?path=link.md")[0], 403, "a symlink out of the folder")

    def test_errors_are_json_with_the_api_number(self):
        for method, target, body, code in (("GET", "/api/nothing", None, 404), ("DELETE", "/api/project", None, 405),
                                          ("POST", "/api/render", b"{not json", 400), ("POST", "/api/file", b"[1]", 400),
                                          ("GET", "/api/file", None, 400), ("GET", "/api/file?path=ghost.md", None, 404)):
            status, answer = self.core.handle(method, target, body)
            self.assertEqual((status, answer["api"]), (code, API_VERSION), (method, target))
            self.assertTrue(answer["error"] and answer["code"])

    def test_a_binary_file_is_not_text(self):
        (self.root / "x.png").write_bytes(b"\x89PNG\xff\xfe\x00")
        self.assertEqual(self.get("/api/file?path=x.png")[0], 415)


class ExcerptHandlers(Folder):
    def test_excerpt_requests_and_cli_share_the_record_operations(self):
        document = self.root / "report.md"
        source = self.root / "sub" / "source.pdf"
        source.write_bytes(b"%PDF-1.4 synthetic")

        def api(method, target, body=None, status=200):
            actual, answer = self.core.handle(method, target, body)
            self.assertEqual(actual, status, answer)
            self.assertEqual(answer["api"], API_VERSION)
            return answer

        source_request = {"key": "a", "file": "sub/source.pdf", "pages": [[2, "41"]]}
        api("POST", "/api/excerpts/sources", source_request, status=201)
        made = api("POST", "/api/excerpts", {"key": "a", "parts": [{"pdf-page": 2, "text": "Café",
                   "text-from": "pdf", "boxes": [[1, 2, 3, 4]]}]}, status=201)
        self.assertEqual(made["markers"], ["[@x:1]", "[@a#1]"])
        self.assertEqual(api("PUT", "/api/excerpts?id=1", {"note": "A note"})["page"], "41")
        document.write_text("Cited [@a#1].\n", encoding="utf-8")
        listing = api("GET", "/api/excerpts")
        self.assertEqual(listing["record"]["excerpts"][0]["note"], "A note")
        self.assertEqual(listing["locations"][0]["file"], "report.md")
        self.assertEqual(listing["locations"][0]["id"], 1)
        self.assertEqual(listing["problems"], api("GET", "/api/excerpts/check")["problems"])
        self.assertIn("excerpt-box", {item["code"] for item in listing["problems"]})
        api("DELETE", "/api/excerpts?id=1", status=409)
        api("PUT", "/api/excerpts?id=0", {"note": "A note"}, status=400)
        api("PUT", "/api/excerpts?id=7", {"note": "A note"}, status=404)

        def cli(method, target, body=None):
            return subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--api", method, target,
                                   *([json.dumps(body)] if body is not None else [])], cwd=self.root,
                                  capture_output=True, timeout=30)

        for target, expected in (("/api/excerpts", listing), ("/api/excerpts/check", api("GET", "/api/excerpts/check"))):
            done = cli("GET", target)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(json.loads(done.stdout), expected)
        done = cli("GET", "/api/source?key=a")
        self.assertEqual((done.returncode, done.stdout), (0, source.read_bytes()), done.stderr)
        done = cli("DELETE", "/api/excerpts?id=1", {"detach": True})
        self.assertEqual((done.returncode, json.loads(done.stdout)["removed"]), (0, 1), done.stderr)
        self.assertEqual(document.read_text(encoding="utf-8"), "Cited [@a, p. 41].\n")
        done = cli("POST", "/api/excerpts/sources", source_request)
        self.assertEqual((done.returncode, json.loads(done.stdout)["pages"]), (0, [[2, "41"]]), done.stderr)
        done = cli("POST", "/api/excerpts", {"key": "a"})
        self.assertEqual((done.returncode, json.loads(done.stdout)["id"]), (0, 2), done.stderr)
        done = cli("PUT", "/api/excerpts?id=2", {"note": "Edited from the API command"})
        self.assertEqual((done.returncode, json.loads(done.stdout)["note"]), (0, "Edited from the API command"), done.stderr)
        self.assertEqual(api("GET", "/api/excerpts")["record"]["excerpts"], [
            {key: value for key, value in json.loads(done.stdout).items() if key != "api"}
        ])

    def test_excerpt_paths_outside_the_project_are_refused(self):
        outside = self.root.parent / "outside.pdf"
        outside.write_bytes(b"%PDF-1.4 private")
        sources = "/api/excerpts/sources"
        self.assertEqual(self.core.handle("POST", sources, {"key": "a", "file": "../outside.pdf"})[0], 403)
        record = self.root / "excerpts.json"
        record.write_text(json.dumps({"pdfmd-excerpts": 1, "next-id": 1, "excerpts": [],
                                     "sources": {"a": {"file": str(outside)}}}), encoding="utf-8")
        for method, target, body in (("GET", "/api/excerpts", None), ("GET", "/api/excerpts/check", None),
                                     ("GET", "/api/source?key=a", None), ("POST", "/api/excerpts", {"key": "a"})):
            status, answer = self.core.handle(method, target, body)
            self.assertEqual((status, answer.get("code")), (403, "outside"), answer)
            self.assertNotIn(str(outside), json.dumps(answer))
        other = self.root.parent / "outside.json"
        other.write_text("private", encoding="utf-8")
        folder = self.root / "sub"
        (folder / ".pdfmd").mkdir()
        (folder / ".pdfmd" / "config.yaml").write_text("options: {excerpts: ../../outside.json}\n", encoding="utf-8")
        self.assertEqual(Core(folder).handle("GET", "/api/excerpts")[0], 403)

    def test_source_http_handler_sends_only_the_requested_pdf_bytes(self):
        from pdfmd_serve.shell import Handler

        contents = b"%PDF-1.4 synthetic"
        (self.root / "named.pdf").write_bytes(contents)
        self.core.handle("POST", "/api/excerpts/sources", {"key": "a", "file": "named.pdf"})
        request = Handler.__new__(Handler)
        request.path, request.command, request.wfile = "/api/source?key=a", "GET", io.BytesIO()
        request.server = SimpleNamespace(core=self.core, token="test", hosts={"localhost:1234"})
        request.headers = {"Host": "localhost:1234", "Range": "bytes=1-4"}
        request.send_head, request.send_json, request.send = mock.Mock(), mock.Mock(), mock.Mock()
        request.handle_any()
        self.assertEqual(request.send.call_args.args[0], 403)
        request.send_head.assert_not_called()
        request.headers["Authorization"] = "Bearer test"
        request.handle_any()
        request.send_head.assert_called_once_with(206, 4, "application/pdf",
                                                  {"Accept-Ranges": "bytes", "Content-Range": f"bytes 1-4/{len(contents)}"})
        self.assertEqual(request.wfile.getvalue(), b"PDF-")
        request.headers["Range"] = "bytes=100-"
        request.handle_any()
        status, body, headers = request.send_json.call_args.args
        self.assertEqual((status, body["code"], headers["Content-Range"]), (416, "range", f"bytes */{len(contents)}"))

    def test_concurrent_excerpt_writes_use_the_command_lock(self):
        from pdfmd_excerpts.record import locked

        record = self.root / "excerpts.json"
        with ThreadPoolExecutor(max_workers=2) as pool:
            with locked(record):
                writes = [pool.submit(self.core.handle, "POST", "/api/excerpts", {"key": "a"}) for _ in range(2)]
                self.assertFalse(any(item.done() for item in writes))
            answers = [item.result(timeout=15) for item in writes]
        self.assertEqual([status for status, _ in answers], [201, 201], answers)
        self.assertEqual(sorted(answer["id"] for _, answer in answers), [1, 2])
        self.assertEqual(json.loads(record.read_text(encoding="utf-8"))["next-id"], 3)


class PreviewCopies(Folder):
    def test_existing_hidden_copy_is_preserved(self):
        existing = self.root / ".pdfmd-live-report.md"
        existing.write_text("keep\n", encoding="utf-8")
        with self.core.document_file(self.root / "report.md", self.root, "unsaved\n") as copy:
            self.assertNotEqual(copy, existing)
            self.assertEqual(copy.parent, self.root)
            self.assertEqual(copy.suffix, ".md")
            self.assertEqual(copy.read_text(), "unsaved\n")
        self.assertFalse(copy.exists())
        self.assertEqual(existing.read_text(), "keep\n")

    def test_existing_symlink_and_its_target_are_preserved(self):
        victim = self.root.parent / "victim.md"
        victim.write_text("keep\n", encoding="utf-8")
        existing = self.root / ".pdfmd-live-report.md"
        existing.symlink_to(victim)
        with self.core.document_file(self.root / "report.md", self.root, "unsaved\n"):
            self.assertEqual(victim.read_text(), "keep\n")
        self.assertTrue(existing.is_symlink())
        self.assertEqual(victim.read_text(), "keep\n")

    def test_overlapping_renders_get_independent_copies_and_cleanup(self):
        with self.core.document_file(self.root / "report.md", self.root, "first\n") as first:
            with self.core.document_file(self.root / "report.md", self.root, "second\n") as second:
                self.assertNotEqual(first, second)
                self.assertEqual(first.read_text(), "first\n")
                self.assertEqual(second.read_text(), "second\n")
            self.assertFalse(second.exists())
            self.assertEqual(first.read_text(), "first\n")
        self.assertFalse(first.exists())

    def test_exclusive_creation_skips_a_symlink_collision(self):
        victim = self.root.parent / "victim.md"
        victim.write_text("keep\n", encoding="utf-8")
        collision = self.root / ".pdfmd-live-occupied-report.md"
        collision.symlink_to(victim)
        with mock.patch("tempfile._get_candidate_names", return_value=iter(("occupied", "fresh"))):
            with self.core.document_file(self.root / "report.md", self.root, "unsaved\n") as copy:
                self.assertEqual(copy.name, ".pdfmd-live-fresh-report.md")
        self.assertTrue(collision.is_symlink())
        self.assertEqual(victim.read_text(), "keep\n")

    def test_cleanup_leaves_a_replacement_file_alone(self):
        with self.core.document_file(self.root / "report.md", self.root, "unsaved\n") as copy:
            copy.rename(self.root / "moved.md")
            copy.write_text("replacement\n", encoding="utf-8")
        self.assertEqual(copy.read_text(), "replacement\n")

    def test_exception_cleans_up_its_copy(self):
        with self.assertRaisesRegex(RuntimeError, "filter failed"):
            with self.core.document_file(self.root / "report.md", self.root, "unsaved\n") as copy:
                raise RuntimeError("filter failed")
        self.assertFalse(copy.exists())

    def test_unwritable_folder_falls_back_and_cleans_up(self):
        with mock.patch("pdfmd_serve.core.tempfile.NamedTemporaryFile", side_effect=PermissionError):
            with self.core.document_file(self.root / "report.md", self.root, "unsaved\n") as copy:
                self.assertNotEqual(copy.parent, self.root)
                self.assertEqual(copy.read_text(), "unsaved\n")
        self.assertFalse(copy.exists())

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_warnings_keep_the_source_name(self):
        @contextlib.contextmanager
        def filters(document, metadata):
            print(f"WARN  {document}: sample warning", file=sys.stderr)
            yield []
        status, answer = Core(self.root, filters=filters).handle(
            "POST", "/api/render", {"path": "report.md", "text": "unsaved\n"})
        self.assertEqual(status, 200, answer)
        self.assertEqual(answer["warnings"], ["WARN  report.md: sample warning"])

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_cli_preview_preserves_existing_symlink(self):
        victim = self.root.parent / "victim.md"
        victim.write_text("keep\n", encoding="utf-8")
        existing = self.root / ".pdfmd-live-report.md"
        existing.symlink_to(victim)
        env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
               **{key: str(self.root.parent / key) for key in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME")}}
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--api", "POST", "/api/render",
                               json.dumps({"path": "report.md", "text": "# Unsaved\n"})],
                              cwd=self.root, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Unsaved", json.loads(done.stdout)["html"])
        self.assertTrue(existing.is_symlink())
        self.assertEqual(victim.read_text(), "keep\n")


class Render(Folder):
    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_project_images_are_resolved_relative_to_the_document(self):
        (self.root / "figs").mkdir()
        (self.root / "figs" / "bird plot.png").write_bytes(b"image bytes")
        text = '![plot](../figs/bird%20plot.png)\n\n![remote](https://example.org/a.png)\n'
        status, answer = self.core.handle("POST", "/api/render", {"path": "sub/n.md", "text": text})
        self.assertEqual(status, 200, answer)
        self.assertIn('/api/raw?path=figs%2Fbird+plot.png', answer["html"])
        self.assertIn('https://example.org/a.png', answer["html"])
        self.assertEqual(self.core.raw({"path": "figs/bird plot.png"})[0], b"image bytes")
        status, answer = self.core.handle("POST", "/api/render", {"path": "sub/n.md", "text": '![plot](figs/bird%20plot.png)'})
        self.assertEqual(status, 200, answer)
        self.assertIn('/api/raw?path=figs%2Fbird+plot.png', answer["html"])

    def test_preview_image_rewriting_respects_attributes_and_containment(self):
        outside = self.root.parent / "outside.png"
        outside.write_bytes(b"outside")
        (self.root / "escape.png").symlink_to(outside)
        markup = ('<img alt="src=\'decoy.png\'" src="figs/a.png?x=1&amp;y=2#part">'
                  '<img src="escape.png"><img src="../outside.png">'
                  '<script>const x = \"<img src=\"fake.png\">\";</script><!-- <img src="fake.png"> -->')
        result = self.core.preview_images(markup, self.root)
        self.assertIn('alt="src=\'decoy.png\'"', result)
        self.assertIn('src="/api/raw?x=1&amp;y=2&amp;path=figs%2Fa.png#part"', result)
        self.assertIn('src="escape.png"', result)
        self.assertIn('src="../outside.png"', result)
        self.assertEqual(result.count('fake.png'), 2)

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_cli_preview_keeps_unicode_separators_before_images(self):
        text = "Before\u2028after\n\n![bird](bird.png)\n"
        (self.root / "bird.png").write_bytes(b"picture")
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--api", "POST", "/api/render",
                               json.dumps({"path": "report.md", "text": text})], cwd=self.root, env={**os.environ},
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        markup = json.loads(done.stdout)["html"]
        self.assertIn("Before\u2028after</p>", markup)
        self.assertRegex(markup, r'<p[^>]*><img src="/api/raw\?path=bird.png"[^>]* alt="bird" /></p>')
        self.assertEqual(markup.count("<img "), 1)
        self.assertNotIn('src="bird.png"', markup)

    def test_without_pandoc_the_answer_says_so(self):
        core = Core(self.root, which=lambda name: None)
        status, answer = core.handle("POST", "/api/render", {"text": "# x"})
        self.assertEqual((status, answer["code"]), (503, "no_pandoc"))

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_render_gives_blocks_with_positions_and_no_word_wrappers(self):
        status, answer = self.core.handle("POST", "/api/render", {"path": "report.md", "text": "# Hi\n\nSee *this* and $x^2$.\n\n- a\n- b\n"})
        self.assertEqual(status, 200, answer)
        self.assertIn('<h1 data-pos="report.md@1:1-2:1"', answer["html"])
        # the form the page's source mirror reads (js/app.js blockLines): `name@line:col-line:col`
        import re
        self.assertTrue(all(re.search(r"@(\d+):\d+-(\d+):(\d+)$", position) for position in re.findall(r'data-pos="([^"]*)"', answer["html"])))
        _, nameless = self.core.handle("POST", "/api/render", {"text": "# Hi\n"})
        self.assertIn('data-pos="@1:1-2:1"', nameless["html"])
        self.assertIn("<em>this</em>", answer["html"])
        self.assertNotIn("data-wrapper", answer["html"])
        self.assertIn("<math", answer["html"])
        self.assertEqual(answer["warnings"], [])

    def test_the_word_wrappers_of_an_older_pandoc_go_too(self):
        """Pandoc 3.1.3 does not mark a wrapper (`data-wrapper="1"`): it is the span with a position and nothing else. A span of the
        author's own keeps its tag on both, and so does the block that carries the position."""
        from pdfmd_serve.core import strip_wrappers
        old = ('<div data-pos="3:1-4:1">\n<p><span data-pos="3:1-3:4">See</span><span data-pos="3:4-3:5"> </span><span data-pos="3:5-3:11">'
               '<em><span data-pos="3:6-3:10">this</span></em></span> <span class="x" data-pos="3:12-3:15">own</span></p>\n</div>')
        self.assertEqual(strip_wrappers(old), '<div data-pos="3:1-4:1">\n<p>See <em>this</em> <span class="x" data-pos="3:12-3:15">own</span></p>\n</div>')
        new = '<p data-pos="3:1-4:1"><span data-wrapper="1" data-pos="3:1-3:4">See</span> <span class="x" data-pos="3:5-3:8">own</span></p>'
        self.assertEqual(strip_wrappers(new), '<p data-pos="3:1-4:1">See <span class="x" data-pos="3:5-3:8">own</span></p>')

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_a_csv_block_is_a_table_when_the_core_is_given_pdfmds_filters(self):
        import pdfmd
        (self.root / "tables").mkdir()
        (self.root / "tables" / "t.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        (self.root / "parts").mkdir()
        text = '::: {#tbl:t .csv file="tables/t.csv" caption="Cap"}\n:::\n'
        _, plain = Core(self.root).handle("POST", "/api/render", {"path": "parts/p.md", "text": text})
        self.assertNotIn("<table", plain["html"])                                 # the core alone is pandoc: no pdfmd syntax
        _, with_filter = Core(self.root, filters=pdfmd.serve_live_filters).handle("POST", "/api/render", {"path": "parts/p.md", "text": text})
        self.assertIn("<th>a</th>", with_filter["html"])                          # the file is found at the project's folder, from a part in parts/
        # `#tbl:t` is pandoc-crossref's: where it is installed, the live view numbers the caption as a build does
        caption = "Table 1: Cap" if shutil.which("pandoc-crossref") else "Cap"
        self.assertIn(f"<caption>{caption}</caption>", with_filter["html"])

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_cli_raw_latex_includes_obey_the_live_boundary(self):
        secret = self.root.parent / "outside.tex"
        secret.write_text("SECRET-OUTSIDE", encoding="utf-8")
        (self.root / "inside.tex").write_text("inside-value", encoding="utf-8")
        (self.root / "nested.tex").write_text(r"\input{../outside.tex}", encoding="utf-8")
        for command, name, expected in (("input", "../outside.tex", False), ("include", str(secret), False),
                                        ("input", "nested", False), ("input", "inside", True),
                                        ("input", r"\outside", False), ("input", " ../outside.tex ", False),
                                        ("input", " inside.tex ", True)):
            with self.subTest(command=command, name=name):
                source = "---\npdfmd-options: {raw: true}\n---\n\n```{=latex}\n" + "\\" + command + "{" + name + "}\n```\n"
                done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--api", "POST", "/api/render",
                                       json.dumps({"path": "report.md", "text": source})], cwd=self.root, env={**os.environ},
                                      stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
                self.assertEqual(done.returncode, 0, done.stderr)
                answer = json.loads(done.stdout)
                if expected:
                    self.assertIn("inside-value", answer["html"])
                else:
                    self.assertNotIn("SECRET-OUTSIDE", answer["html"])
                    self.assertTrue(any("outside the project folder" in line for line in answer["warnings"]), answer)

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_fetch_checks_decoded_file_urls(self):
        outside = self.root.parent / "outside.txt"
        outside.write_text("SECRET-OUTSIDE", encoding="utf-8")
        inside = self.root / "inside.txt"
        inside.write_text("inside-value", encoding="utf-8")
        (self.root / "report.lua").write_text('''function Image(el)
  local ok, mime, data = pcall(pandoc.mediabag.fetch, el.src)
  return pandoc.Str(ok and data or "REFUSED")
end
''', encoding="utf-8")
        @contextlib.contextmanager
        def filters(document, metadata):
            yield ["--lua-filter", str(self.root / "report.lua")]
        core = Core(self.root, filters=filters)
        for url, allowed in ((outside.as_uri(), False), (inside.as_uri(), True),
                             (self.root.as_uri() + "/%2e%2e/outside.txt", False),
                             (outside.as_uri().replace("file:///", "file://localhost/"), False)):
            with self.subTest(url=url):
                text = f"![resource]({url})\n"
                (self.root / "report.md").write_text(text, encoding="utf-8")
                status, answer = core.handle("POST", "/api/render", {"path": "report.md", "text": text})
                self.assertEqual(status, 200, answer)
                if allowed:
                    self.assertIn("inside-value", answer["html"])
                else:
                    self.assertNotIn("SECRET-OUTSIDE", answer["html"])
                    self.assertTrue(any("outside the project folder" in line for line in answer["warnings"]), answer)

    @unittest.skipUnless(PANDOC and os.name != "nt", "needs Pandoc and symlinks")
    def test_cli_trusted_cache_symlinks_are_checked_after_resolution(self):
        cache = self.root.parent / "cache" / "pdfmd"
        cache.mkdir(parents=True)
        outside = self.root.parent / "secret.csv"
        outside.write_text("k,v\nSECRET-OUTSIDE,1\n", encoding="utf-8")
        (cache / "safe.csv").write_text("k,v\ncache-value,2\n", encoding="utf-8")
        (cache / "escape.csv").symlink_to(outside)
        (cache / "safe-link.csv").symlink_to(cache / "safe.csv")
        env = {**os.environ, "XDG_CACHE_HOME": str(cache.parent)}
        for name, allowed in (("escape.csv", False), ("safe.csv", True), ("safe-link.csv", True)):
            with self.subTest(name=name):
                text = f'::: {{.csv file="{cache / name}"}}\n:::\n'
                done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--api", "POST", "/api/render",
                                       json.dumps({"path": "report.md", "text": text})], cwd=self.root, env=env,
                                      stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
                self.assertEqual(done.returncode, 0, done.stderr)
                answer = json.loads(done.stdout)
                if allowed:
                    self.assertIn("cache-value", answer["html"])
                else:
                    self.assertNotIn("SECRET-OUTSIDE", answer["html"])
                    self.assertTrue(any("outside the project folder" in line for line in answer["warnings"]), answer)

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_cli_live_diagram_cache_uses_render_folder_outside_project(self):
        text = "---\npdfmd-options: {diagram-timeout: 0}\n---\n\n```dot\ndigraph { a -> b }\n```\n"
        for verbose in (False, True):
            with self.subTest(verbose=verbose):
                cache = self.root.parent / ("verbose-cache" if verbose else "quiet-cache")
                env = {**os.environ, "XDG_CACHE_HOME": str(cache), "LOCALAPPDATA": str(cache)}
                args = ["--verbose"] if verbose else []
                done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), *args, "--api", "POST", "/api/render",
                                       json.dumps({"path": "report.md", "text": text})], cwd=self.root, env=env,
                                      stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
                self.assertEqual(done.returncode, 0, done.stderr)
                answer = json.loads(done.stdout)
                self.assertIn("digraph", answer["html"])
                self.assertFalse((cache / "pdfmd" / "raw" / "pictures").exists(), "a live render must not create the outside cache folder")
                notes = [line for line in answer["warnings"] if "diagram cache" in line and "per-render" in line]
                self.assertEqual(bool(notes), verbose, answer)

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_document_diagram_cache_is_project_local_or_temporary(self):
        probe = self.root / "probe.lua"
        probe.write_text('''function Pandoc(doc)
  local ok = pcall(pandoc.system.list_directory, os.getenv("TMPDIR") .. "/diagrams")
  return pandoc.Pandoc({pandoc.Para({pandoc.Str(ok and "temporary-cache" or "project-cache")})})
end
''', encoding="utf-8")
        @contextlib.contextmanager
        def filters(document, metadata):
            yield ["--lua-filter", str(ROOT / "lib/pdfmd_lua/diagram.lua"), "--lua-filter", str(probe)]
        core = Core(self.root, filters=filters)
        for folder, temporary in ((self.root.parent / "outside-cache", True), (self.root / "local-cache", False)):
            with self.subTest(folder=folder.name):
                text = "---\npdfmd-raw-cache: " + json.dumps(str(folder)) + "\npdfmd-diagram-off: true\n---\n\n```dot\nx\n```\n"
                status, answer = core.handle("POST", "/api/render", {"path": "report.md", "text": text})
                self.assertEqual(status, 200, answer)
                self.assertIn("temporary-cache" if temporary else "project-cache", answer["html"])
                self.assertEqual(folder.exists(), not temporary)

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_the_live_views_filters_open_nothing_outside_the_project(self):
        """Review finding G4.4: the text names the files a filter opens (`::: {.csv file=...}`). A name that leads out of the project, by
        `..`, by an absolute path or through a symlink, is refused with a warning; a file of the project is still a table."""
        import pdfmd
        secret = self.root.parent / "secret.csv"
        secret.write_text("k,v\nSECRET-OUTSIDE,1\n", encoding="utf-8")
        (self.root / "inside.csv").write_text("k,v\ninside-value,2\n", encoding="utf-8")
        core = Core(self.root, filters=pdfmd.serve_live_filters, places=lambda: [pdfmd.cache_root()])
        names = ["../secret.csv", secret.as_posix(), "sub/../../secret.csv"]
        if os.name != "nt":
            (self.root / "link.csv").symlink_to(secret)
            (self.root / "out").symlink_to(self.root.parent, target_is_directory=True)
            (self.root / "sub" / "up").symlink_to(self.root, target_is_directory=True)     # a link that stays inside, then `..` out
            names += ["link.csv", "out/secret.csv", "sub/up/../secret.csv"]
        for name in names:
            with self.subTest(name=name):
                status, answer = core.handle("POST", "/api/render", {"path": "report.md", "text": f'::: {{.csv file="{name}"}}\n:::\n'})
                self.assertEqual(status, 200, answer)
                self.assertNotIn("SECRET-OUTSIDE", answer["html"])
                self.assertTrue(any("outside the project folder" in line for line in answer["warnings"]), answer["warnings"])
        for document, name in (("sub/n.md", "../inside.csv"), ("report.md", (self.root / "inside.csv").as_posix())):
            with self.subTest(inside=name):
                status, answer = core.handle("POST", "/api/render", {"path": document, "text": f'::: {{.csv file="{name}"}}\n:::\n'})
                self.assertEqual(status, 200, answer)
                self.assertIn("inside-value", answer["html"])
                self.assertFalse(any("outside the project folder" in line for line in answer["warnings"]), answer["warnings"])

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_the_live_view_shows_pdfmds_syntax_as_a_build_does(self):
        """Calc (an inline `{=}` and a `::: calc` div: both need the document as the reader gives it, which `sourcepos` changes), callouts and
        page breaks come from the one list every build uses, and what is not saved yet is read from the text, not from the file."""
        import pdfmd
        core = Core(self.root, filters=pdfmd.serve_live_filters)
        (self.root / "parts").mkdir()
        saved = "A half is `1/2`{=}.\n\n::: calc\nV = 7 - 2 = {ans} mL\n:::\n"
        (self.root / "parts" / "p.md").write_text(saved, encoding="utf-8")
        for text in (saved, saved + "\n> [!NOTE]\n> Careful.\n\n<!-- pagebreak -->\n"):          # the second is not on disk
            with self.subTest(unsaved=text != saved):
                status, answer = core.handle("POST", "/api/render", {"path": "parts/p.md", "text": text})
                self.assertEqual(status, 200, answer)
                self.assertIn("A half is 0.5.", answer["html"])
                self.assertIn("V = 7 - 2 = 5 mL", answer["html"])
                self.assertNotIn("{ans}", answer["html"])
                self.assertNotIn("data-wrapper", answer["html"])
        self.assertIn('class="callout', answer["html"])
        self.assertIn("page-break-after", answer["html"])
        self.assertEqual(sorted(p.name for p in (self.root / "parts").iterdir()), ["p.md"], "no copy of the text is left in the folder")

    def test_every_build_and_the_live_view_take_the_filters_from_one_list(self):
        """Entry 3do: a syntax of pdfmd's own is added to document_filter_args() once and shows in every writer and in the live view. A
        build site that writes the filters out itself again would be the second list this guards against."""
        import ast
        from source_support import python_sources

        def called(call: ast.Call) -> str:
            # `x(...)` in pdfmd.py, `core.x(...)` in a package that was handed the pdfmd module (entry 3fi: the split)
            if isinstance(call.func, ast.Name):
                return call.func.id
            if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) and call.func.value.id == "core":
                return call.func.attr
            return ""

        trees = [ast.parse(path.read_text(encoding="utf-8")) for path in python_sources()]
        helpers = {"metadata_append_args", "md_macro_args", "csv_table_filter_args", "pagebreak_filter_args", "indent_filter_args",
                   "markup_filter_args", "table_caption_args", "linebreak_args", "title_filter_args", "cover_filter_args",
                   "raw_filter_args", "crossref_filter_args"}
        # pdfmd.py and lib/: report mode (lib/pdfmd_report) wrote the list out itself until 3.32.53, out of this test's sight
        callers: dict[str, set] = {name: set() for name in helpers}
        for tree in trees:
            for function in ast.walk(tree):
                if isinstance(function, ast.FunctionDef):
                    for call in ast.walk(function):
                        if isinstance(call, ast.Call) and called(call) in callers:
                            callers[called(call)].add(function.name)
        self.assertEqual({name: sorted(where) for name, where in callers.items()},
                         {name: ["document_filter_args"] for name in helpers})
        live = [node for tree in trees for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "serve_live_filters"]
        self.assertEqual(len(live), 1, "serve_live_filters is defined once, in pdfmd.py or a package")
        self.assertIn("document_filter_args", {called(call) for call in ast.walk(live[0]) if isinstance(call, ast.Call)})

    @unittest.skipUnless(PANDOC, "needs Pandoc")
    def test_render_of_what_is_not_written_yet(self):
        status, answer = self.core.handle("POST", "/api/render", {"text": "**unclosed"})
        self.assertEqual(status, 200)
        self.assertIn("**unclosed", answer["html"])


class PageFixtures(unittest.TestCase):
    def test_the_fixtures_name_the_endpoints_the_api_has(self):
        """The page's api.js calls these; each is a route of the core (a rename on one side fails here)."""
        from pdfmd_serve.core import ROUTES
        source = (WEB / "js" / "api.js").read_text(encoding="utf-8")
        for method, path in ROUTES:
            self.assertIn(path.split("?")[0], source, f"{method} {path} is not called by js/api.js")

    def test_the_page_is_all_there(self):
        for name in ("index.html", "css/app.css", "js/api.js", "js/app.js", "js/editor.js", "js/native.js", "fixtures/fixtures.js", "vendor/cm/codemirror.js", "__init__.py"):
            self.assertTrue((WEB / name).is_file(), name)


class UnreadRefusals(unittest.TestCase):
    """Exercise the refusal and cleanup without binding a socket (also runs in the sandbox)."""

    def handler(self, length="100000", limit=64):
        from pdfmd_serve.shell import Handler
        handler = Handler.__new__(Handler)
        handler.headers = {"Content-Length": length}
        handler.server = SimpleNamespace(max_body=limit)
        handler.connection = mock.Mock()
        handler.rfile = mock.Mock()
        handler.rfile.read1.return_value = b""
        handler.wfile = mock.Mock()
        handler.refuse = mock.Mock()
        return handler

    def test_unread_refusals_send_then_half_close_before_discarding(self):
        import socket
        for length, limit, status in (("100000", 64, 413), ("100000", 0, 403), ("-1", 64, 400), ("invalid", 64, 400)):
            with self.subTest(length=length, limit=limit):
                handler = self.handler(length, limit)
                events = mock.Mock()
                for name in ("refuse", "wfile", "connection", "rfile"):
                    events.attach_mock(getattr(handler, name), name)
                handler.handle_any()
                self.assertEqual(handler.refuse.call_args.args[0], status)
                self.assertTrue(handler.close_connection)
                handler.rfile.read.assert_not_called()
                handler.connection.shutdown.assert_called_once_with(socket.SHUT_WR)
                calls = events.mock_calls
                self.assertEqual(calls[0][0], "refuse", "the response precedes all transport cleanup")
                self.assertLess(calls.index(mock.call.wfile.flush()), calls.index(mock.call.connection.shutdown(socket.SHUT_WR)))
                self.assertLess(calls.index(mock.call.connection.shutdown(socket.SHUT_WR)),
                                next(i for i, call in enumerate(calls) if call[0] == "rfile.read1"))

    def test_discard_has_a_byte_budget_even_when_the_peer_keeps_sending(self):
        from pdfmd_serve.shell import MAX_REQUEST_MB
        handler = self.handler()
        discarded = 0

        def read(size):
            nonlocal discarded
            discarded += size
            self.assertLessEqual(discarded, MAX_REQUEST_MB * 1024 * 1024)
            return b"x" * size

        handler.rfile.read1.side_effect = read
        with mock.patch("time.monotonic", return_value=0):
            handler.handle_any()
        self.assertEqual(discarded, MAX_REQUEST_MB * 1024 * 1024)

    def test_discard_has_an_absolute_deadline_even_when_the_peer_trickles(self):
        handler = self.handler()
        handler.rfile.read1.return_value = b"x"
        with mock.patch("time.monotonic", side_effect=(0, 0, 0.75, 2)):
            handler.handle_any()
        self.assertEqual(handler.rfile.read1.call_count, 2)
        waits = [call.args[0] for call in handler.connection.settimeout.call_args_list]
        self.assertEqual(len(waits), 2)
        self.assertGreater(waits[0], waits[1], "each read gets only the time left, not a fresh timeout")

    def test_a_stalled_or_disconnected_peer_does_not_escape_cleanup(self):
        for error in (TimeoutError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            with self.subTest(error=error):
                handler = self.handler()
                handler.rfile.read1.side_effect = error
                handler.handle_any()
                handler.rfile.read1.assert_called_once()

    def test_an_interrupted_body_read_also_half_closes(self):
        import socket
        handler = self.handler(length="32")
        handler.rfile.read.side_effect = ConnectionResetError
        handler.handle_any()
        self.assertEqual(handler.refuse.call_args.args[0], 400)
        handler.connection.shutdown.assert_called_once_with(socket.SHUT_WR)

    def test_the_client_still_requires_a_response_after_each_os_send_error(self):
        response = b"HTTP/1.1 413 Request Entity Too Large\r\n\r\n"
        for error in (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            with self.subTest(error=error), mock.patch("socket.create_connection") as connect:
                sock = connect.return_value.__enter__.return_value
                sock.sendall.side_effect = error
                sock.recv.side_effect = (response, b"")
                self.assertEqual(Http.raw_request(1234, "request"), response)

    def test_the_client_keeps_a_response_before_each_os_receive_error(self):
        response = b"HTTP/1.1 413 Request Entity Too Large\r\n\r\n"
        for error in (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            with self.subTest(error=error), mock.patch("socket.create_connection") as connect:
                sock = connect.return_value.__enter__.return_value
                sock.recv.side_effect = (response, error)
                self.assertEqual(Http.raw_request(1234, "request"), response)


class Http(Folder):
    def setUp(self):
        super().setUp()
        self.server = Server(self.core, WEB, "tok-123")
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.port = self.server.server_address[1]

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def ask(self, method, path, body=None, headers=None, host=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = dict(headers or {})
        headers.setdefault("Host", host or f"127.0.0.1:{self.port}")
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def bearer(self):
        return {"Authorization": "Bearer tok-123"}

    @staticmethod
    def raw_request(port, head: str) -> bytes:
        """Send the supplied request, then collect the answer across packets, including after a refused upload interrupts sending.
        A header-only refusal must answer without waiting for the body; a server that waits for it times out here."""
        import socket
        answer = b""
        with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
            try:
                sock.sendall(head.encode("ascii"))
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass        # a refused upload can fail while sending; still require the response below
            while True:
                try:
                    chunk = sock.recv(65536)
                except (socket.timeout, ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                    break
                if not chunk:
                    break
                answer += chunk
        return answer

    def test_a_body_over_the_limit_or_a_negative_length_is_refused_unread(self):
        server = Server(self.core, WEB, "tok-123", max_body=64)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(5)))
        port = server.server_address[1]
        huge = self.raw_request(port, f"PUT /api/file HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Length: {10 ** 12}\r\n\r\n")
        self.assertIn(b" 413 ", huge.split(b"\r\n")[0], "answered at once, without waiting for (or allocating) the body")
        self.assertIn(b"serve-max-request-mb", huge)
        negative = self.raw_request(port, f"PUT /api/file HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Length: -1\r\n\r\n")
        self.assertIn(b" 400 ", negative.split(b"\r\n")[0], "read(-1) would wait for the end of the connection")
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)     # a body within the limit still goes through
        connection.request("POST", "/api/file", body=json.dumps({"path": "small.md", "text": "x"}),
                           headers={"Authorization": "Bearer tok-123", "Host": f"127.0.0.1:{port}"})
        self.assertEqual(answer_status(connection), 201)
        connection.close()

    def _serve_with(self, max_body):
        server = Server(self.core, WEB, "tok-123", max_body=max_body)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(5)))
        return server.server_address[1]

    def _post_file(self, port, text="x"):
        body = json.dumps({"path": "new.md", "text": text})
        return self.raw_request(port, f"POST /api/file HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAuthorization: Bearer tok-123\r\n"
                                      f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n{body}")

    def test_a_request_limit_of_zero_switches_bodies_off_and_reading_still_works(self):
        port = self._serve_with(0)
        answer = self._post_file(port)
        self.assertIn(b" 403 ", answer.split(b"\r\n")[0])
        self.assertIn(b"serve-max-request-mb", answer)
        self.assertIn(b"switches bodies off", answer)
        self.assertIn(b"bodies_off", answer)
        self.assertFalse((self.root / "new.md").exists(), "nothing was written")
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        connection.request("GET", "/api/project", headers={"Authorization": "Bearer tok-123"})
        self.assertEqual(answer_status(connection), 200)
        connection.close()

    def test_a_negative_request_limit_is_no_limit_and_a_positive_one_is_the_cap(self):
        unbound = self._serve_with(None)        # what a negative number becomes
        self.assertIn(b" 201 ", self._post_file(unbound, "x" * 100000).split(b"\r\n")[0])
        capped = self._serve_with(64)
        self.assertIn(b" 413 ", self._post_file(capped, "x" * 100000).split(b"\r\n")[0])

    def test_large_unread_bodies_deliver_the_refusal(self):
        body = "x" * (4 * 1024 * 1024)        # larger than the TCP socket buffers, not just a header-only refusal
        for limit, length, status, code in ((64, str(len(body)), 413, "too_large"),
                                          (0, str(len(body)), 403, "bodies_off"),
                                          (64, "-1", 400, "length"), (64, "invalid", 400, "length")):
            port = self._serve_with(limit)
            for attempt in range(3):
                with self.subTest(limit=limit, length=length, attempt=attempt):
                    answer = self.raw_request(port, f"POST /api/file HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                                                   f"Content-Length: {length}\r\n\r\n{body}")
                    self.assertIn(f" {status} ".encode(), answer.split(b"\r\n")[0])
                    self.assertEqual(json.loads(answer.split(b"\r\n\r\n", 1)[1])["code"], code)
        self.assertFalse((self.root / "new.md").exists())

    def test_the_setup_value_of_the_request_limit_zero_negative_positive(self):
        # 0.000000001 MB is under one byte: a cap of one byte (413), never 0, which would switch bodies off (403)
        for value, small, big in ((0, 403, 403), (-1, 201, 201), (0.001, 201, 413), ("0.000000001", 413, 413)):
            config = self.root / f"config{value}.yaml"
            config.write_text(f"options:\n  serve-max-request-mb: {value}\n", encoding="utf-8")
            process = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--serve"], cwd=self.root, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                       env={**os.environ, "PDFMD_CONFIG": str(config)})
            try:
                info = json.loads(process.stdout.readline())
                for text, status in (("x", small), ("x" * 4000, big)):
                    connection = http.client.HTTPConnection("127.0.0.1", info["port"], timeout=30)
                    connection.request("POST", "/api/file", body=json.dumps({"path": f"n{value}-{len(text)}.md", "text": text}),
                                       headers={"Authorization": "Bearer " + info["token"], "Content-Type": "application/json"})
                    self.assertEqual(answer_status(connection), status, f"limit {value}, {len(text)} characters")
                    connection.close()
            finally:
                process.terminate()
                process.communicate(timeout=30)

    @unittest.skipUnless(os.name == "posix", "a watched process is seen on POSIX only")
    def test_the_server_watches_only_the_process_it_is_told_about(self):
        import io
        from contextlib import redirect_stderr
        from unittest import mock
        from pdfmd_serve.shell import ParentGone
        clean = {key: value for key, value in os.environ.items() if key != "PDFMD_SERVE_PARENT"}
        with mock.patch.dict(os.environ, clean, clear=True):
            server = Server(self.core, WEB, "tok-123")
            self.addCleanup(server.server_close)
            self.assertIsNone(server.parent, "no variable: nothing is watched")
            server.service_actions()
        with mock.patch.dict(os.environ, {"PDFMD_SERVE_PARENT": str(os.getpid())}):
            watched = Server(self.core, WEB, "tok-123")
            self.addCleanup(watched.server_close)
            self.assertEqual(watched.parent, os.getpid())
            watched.service_actions()                                  # it exists: nothing happens
            watched.parent = 2 ** 22 + 12345                           # a process that is not there
            with self.assertRaises(ParentGone):
                watched.service_actions()
        for bad in ("abc", "0", "-5", "1.5"):
            with mock.patch.dict(os.environ, {"PDFMD_SERVE_PARENT": bad}), redirect_stderr(io.StringIO()) as err:
                server = Server(self.core, WEB, "tok-123")
                self.addCleanup(server.server_close)
                self.assertIsNone(server.parent, bad)
                self.assertEqual(err.getvalue().count("WARN"), 1, bad)

    def test_it_listens_on_the_loopback_only(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_no_token_no_answer(self):
        self.assertEqual(self.ask("GET", "/")[0], 403)
        self.assertEqual(self.ask("GET", "/api/project")[0], 403)
        self.assertEqual(self.ask("GET", "/api/project", headers={"Authorization": "Bearer wrong"})[0], 403)
        self.assertEqual(self.ask("GET", "/?t=wrong")[0], 403)

    def test_the_printed_url_trades_the_token_for_a_cookie(self):
        status, headers, _ = self.ask("GET", "/?t=tok-123")
        self.assertEqual((status, headers["Location"]), (302, "/"))
        cookie = headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        status, _, page = self.ask("GET", "/", headers={"Cookie": cookie.split(";")[0]})
        self.assertEqual(status, 200)
        self.assertIn(b"<title>", page)

    def test_the_page_is_served_with_the_right_types_and_a_policy(self):
        status, headers, _ = self.ask("GET", "/js/app.js", headers=self.bearer())
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/javascript"))
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(self.ask("GET", "/demo/report.md", headers=self.bearer())[0], 404, "the maintainer's demo is not the page")
        self.assertEqual(self.ask("GET", "/../pdfmd.py", headers=self.bearer())[0], 404)
        self.assertEqual(self.ask("GET", "/%2e%2e/%2e%2e/pdfmd.py", headers=self.bearer())[0], 404)

    def test_another_host_name_is_refused(self):
        self.assertEqual(self.ask("GET", "/api/project", headers=self.bearer(), host="evil.example:80")[0], 403)
        self.assertEqual(self.ask("GET", "/api/project", headers=self.bearer(), host=f"localhost:{self.port}")[0], 200)

    def test_a_write_from_another_origin_is_refused(self):
        body = json.dumps({"path": "n.md", "text": "x"})
        status, _, _ = self.ask("POST", "/api/file", body, {**self.bearer(), "Origin": "http://evil.example", "Content-Length": str(len(body))})
        self.assertEqual(status, 403)
        self.assertFalse((self.root / "n.md").exists())
        status, _, _ = self.ask("POST", "/api/file", body, {**self.bearer(), "Origin": f"http://127.0.0.1:{self.port}", "Content-Length": str(len(body))})
        self.assertEqual(status, 201)

    def test_raw_serves_a_picture_and_a_pdf_as_they_are(self):
        (self.root / "sub" / "p.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
        (self.root / "sub" / "b.pdf").write_bytes(b"%PDF-1.4 fake")
        status, headers, body = self.ask("GET", "/api/raw?path=sub/p.png", headers=self.bearer())
        self.assertEqual((status, headers["Content-Type"], body), (200, "image/png", b"\x89PNG\r\n\x1a\nfake"))
        status, headers, body = self.ask("GET", "/api/raw?path=sub/b.pdf", headers=self.bearer())
        self.assertEqual((status, headers["Content-Type"], body), (200, "application/pdf", b"%PDF-1.4 fake"))
        for path, code, why in (("report.md", 415, "not_viewable"), ("sub/none.png", 404, "no_file"), ("../x.png", 403, "outside")):
            status, _, body = self.ask("GET", "/api/raw?path=" + path, headers=self.bearer())
            self.assertEqual((status, json.loads(body)["code"]), (code, why), path)
        status, _, _ = self.ask("GET", "/api/raw?path=sub/p.png")
        self.assertEqual(status, 403)                                            # no token, no picture

    def test_the_api_over_http(self):
        status, _, body = self.ask("GET", "/api/project", headers=self.bearer())
        self.assertEqual((status, json.loads(body)["main"]), (200, "report.md"))
        status, _, body = self.ask("GET", "/api/file?path=../x", headers=self.bearer())
        self.assertEqual((status, json.loads(body)["code"]), (403, "outside"))

    def test_excerpt_source_verifies_the_token_magic_and_range(self):
        contents = b"%PDF-1.4 synthetic"
        (self.root / "signed.data").write_bytes(contents)
        (self.root / "unsigned.pdf").write_bytes(b"not a PDF")
        (self.root / "excerpts.json").write_text(json.dumps({
            "pdfmd-excerpts": 1, "next-id": 1, "excerpts": [],
            "sources": {"good": {"file": "signed.data"}, "bad": {"file": "unsigned.pdf"}},
        }), encoding="utf-8")
        target = "/api/source?" + urlencode({"key": "good"})
        self.assertEqual(self.ask("GET", target)[0], 403)
        self.assertEqual(self.ask("POST", "/api/excerpts", body='{"key":"good"}')[0], 403)
        self.assertEqual(self.ask("GET", target, headers=self.bearer())[2], contents)
        for value, start, end in (("bytes=1-4", 1, 4), ("bytes=7-", 7, len(contents) - 1),
                                  ("bytes=-3", len(contents) - 3, len(contents) - 1)):
            status, headers, payload = self.ask("GET", target, headers={**self.bearer(), "Range": value})
            self.assertEqual((status, headers["Content-Type"], headers["Accept-Ranges"]), (206, "application/pdf", "bytes"))
            self.assertEqual(headers["Content-Range"], f"bytes {start}-{end}/{len(contents)}")
            self.assertEqual(payload, contents[start:end + 1])
        status, headers, payload = self.ask("HEAD", target, headers=self.bearer())
        self.assertEqual((status, headers["Content-Length"], payload), (200, str(len(contents)), b""))
        status, headers, _ = self.ask("GET", target, headers={**self.bearer(), "Range": "bytes=100-"})
        self.assertEqual((status, headers["Content-Range"]), (416, f"bytes */{len(contents)}"))
        self.assertEqual(self.ask("GET", "/api/source?key=bad", headers=self.bearer())[0], 415)
        self.assertEqual(self.ask("GET", "/api/source?key=signed.data", headers=self.bearer())[0], 404)


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name).resolve()
        (self.folder / "a.md").write_text("# A\n\ntext\n", encoding="utf-8")

    def pdfmd(self, *args, env=None, input=None):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *args], cwd=self.folder, capture_output=True, text=True, timeout=120,
                              env=env, input=input, encoding="utf-8")

    def test_api_answers_on_stdout(self):
        done = self.pdfmd("--api", "GET", "/api/project")
        self.assertEqual(done.returncode, 0, done.stderr)
        project = json.loads(done.stdout)
        self.assertEqual((project["main"], project["api"]), ("a.md", API_VERSION))
        self.assertEqual(project["name"], self.folder.name)

    def test_api_exit_code_and_stdin(self):
        self.assertEqual(self.pdfmd("--api", "GET", "/api/file?path=../x").returncode, 1)
        done = self.pdfmd("--api", "POST", "/api/file", "-", input='{"path": "b.md", "text": "# B\\n"}')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((self.folder / "b.md").read_text(encoding="utf-8"), "# B\n")
        self.assertEqual(self.pdfmd("--api", "GET").returncode, 2)
        self.assertEqual(self.pdfmd("--api", "FETCH", "/api/project").returncode, 2)

    def test_render_without_pandoc_on_an_empty_path(self):
        env = {**os.environ, "PATH": ""}
        done = self.pdfmd("--api", "POST", "/api/render", '{"text": "# x"}', env=env)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertEqual(json.loads(done.stdout)["code"], "no_pandoc")

    def test_serve_prints_one_json_line_and_builds_nothing(self):
        (self.folder / "z.md").write_text("# Z\n", encoding="utf-8")        # two documents: bare pdfmd would pick one and build it
        process = subprocess.Popen([sys.executable, str(ROOT / "pdfmd.py"), "--serve"], cwd=self.folder, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding="utf-8")
        try:
            info = json.loads(process.stdout.readline())
            self.assertEqual(set(info), {"api", "url", "port", "token", "root"})
            self.assertTrue(info["url"].startswith(f"http://127.0.0.1:{info['port']}/?t="))
            connection = http.client.HTTPConnection("127.0.0.1", info["port"], timeout=30)
            connection.request("GET", "/api/project", headers={"Authorization": "Bearer " + info["token"]})
            answer = connection.getresponse()
            project = json.loads(answer.read())
            self.assertEqual(answer.status, 200)
            self.assertEqual(sorted(item["name"] for item in project["tree"]), ["a.md", "z.md"])
            connection.close()
            self.assertEqual(sorted(path.name for path in self.folder.iterdir()), ["a.md", "z.md"], "serving builds nothing")
        finally:
            process.terminate()
            process.communicate(timeout=30)

    @unittest.skipUnless(os.name == "posix", "a watched process is seen on POSIX only")
    def test_serve_ends_with_the_process_named_by_pdfmd_serve_parent(self):
        """A crashed Mac app left `pdfmd --serve` idling on its port: the app passes its process id, and the server ends with it."""
        helper = subprocess.Popen(["sleep", "300"])
        self.addCleanup(lambda: (helper.kill(), helper.wait()) if helper.poll() is None else None)
        process = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--serve"], cwd=self.folder, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                   env={**os.environ, "PDFMD_SERVE_PARENT": str(helper.pid)})
        self.addCleanup(lambda: (process.kill(), process.wait()) if process.poll() is None else None)
        self.assertIn('"url"', process.stdout.readline(), "the server started and said where it listens")
        import time
        time.sleep(0.8)
        self.assertIsNone(process.poll(), "the process is alive: the server keeps serving")
        helper.kill()
        helper.wait()                                                  # reaped: a zombie would still answer signal 0
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.fail("the server outlived the process it was told to watch")

    @unittest.skipUnless(os.name == "posix", "a parent that ends is seen on POSIX only")
    def test_serve_without_the_variable_outlives_its_starter(self):
        """A server started by hand (`nohup pdfmd --serve &`): the shell that started it ends and the server keeps serving."""
        import time
        out = self.folder / "serve.out"
        env = {key: value for key, value in os.environ.items() if key != "PDFMD_SERVE_PARENT"}
        done = subprocess.run(["sh", "-c", 'nohup "$1" "$2" --serve >"$3" 2>/dev/null </dev/null & echo $!', "sh", sys.executable,
                               str(ROOT / "scripts" / "pdfmd"), str(out)], cwd=self.folder, capture_output=True, text=True, timeout=60, env=env)
        pid = int(done.stdout.strip())
        self.addCleanup(lambda: _kill(pid))
        deadline = time.monotonic() + 120                              # a cold start on a loaded CI runner can take a while
        while time.monotonic() < deadline and '"url"' not in (out.read_text(encoding="utf-8") if out.exists() else ""):
            time.sleep(0.1)
        announced = out.read_text(encoding="utf-8") if out.exists() else ""
        if '"url"' not in announced:
            self.fail(f"the server never said where it listens; its output: {announced!r}")
        info = json.loads(announced.splitlines()[0])
        time.sleep(1.5)                                                # several turns of the 0.2 s poll after the starter's end
        self.assertTrue(_alive(pid), "an unwatched server must outlive its starter")
        connection = http.client.HTTPConnection("127.0.0.1", info["port"], timeout=30)
        connection.request("GET", "/api/project", headers={"Authorization": "Bearer " + info["token"]})
        self.assertEqual(answer_status(connection), 200)
        connection.close()
        _kill(pid)

    def test_serve_reads_the_request_limit_from_the_setup(self):
        """`serve-max-request-mb` in the config's options: a body over it is refused by `pdfmd --serve` itself."""
        config = self.folder / "config.yaml"
        config.write_text("options:\n  serve-max-request-mb: 0.001\n", encoding="utf-8")        # about 1 KB
        process = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--serve"], cwd=self.folder, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                   env={**os.environ, "PDFMD_CONFIG": str(config)})
        try:
            info = json.loads(process.stdout.readline())
            headers = {"Authorization": "Bearer " + info["token"], "Content-Type": "application/json"}
            for text, status in (("x" * 4000, 413), ("x", 201)):
                connection = http.client.HTTPConnection("127.0.0.1", info["port"], timeout=30)
                connection.request("POST", "/api/file", body=json.dumps({"path": f"n{len(text)}.md", "text": text}), headers=headers)
                self.assertEqual(answer_status(connection), status)
                connection.close()
        finally:
            process.terminate()
            process.communicate(timeout=30)

    def test_large_refused_upload_gets_413_through_the_launcher(self):
        config_home = self.folder / "config"
        config = config_home / "pdfmd" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text("options:\n  serve-max-request-mb: 0.001\n", encoding="utf-8")        # about 1 KB, far under the 4 MB body
        process = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--serve"], cwd=self.folder,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                   env={**os.environ, "PDFMD_CONFIG": str(config), "PDFMD_NO_PROMPT": "1"})
        try:
            announcement = process.stdout.readline()
            self.assertTrue(announcement, "--serve could not start; check whether the sandbox blocks socket binding")
            port = json.loads(announcement)["port"]
            body = "x" * (4 * 1024 * 1024)
            for attempt in range(3):
                with self.subTest(attempt=attempt):
                    answer = Http.raw_request(port, f"POST /api/file HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                                                    f"Content-Length: {len(body)}\r\n\r\n{body}")
                    self.assertIn(b" 413 ", answer.split(b"\r\n")[0])
                    self.assertEqual(json.loads(answer.split(b"\r\n\r\n", 1)[1])["code"], "too_large")
            self.assertEqual(list(self.folder.glob("*.md")), [self.folder / "a.md"], "a refused upload writes nothing")
        finally:
            process.terminate()
            process.communicate(timeout=30)

    def test_serve_wants_a_folder(self):
        done = self.pdfmd("--serve", "no-such-folder")
        self.assertEqual(done.returncode, 2)
        self.assertIn("is not one", done.stderr)


if __name__ == "__main__":
    unittest.main()
