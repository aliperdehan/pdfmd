"""`pdfmd --serve` and `pdfmd --api` (entry 3do): the JSON core, the HTTP shell, the command line, and that the shapes are the ones the page's
fixtures show (the page is built against the fixtures, so a drift here breaks the page)."""

from __future__ import annotations

import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

from pdfmd_serve import API_VERSION, Core, Server  # noqa: E402

PANDOC = shutil.which("pandoc")
WEB = ROOT / "lib" / "pdfmd_web"


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


class Render(Folder):
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

    def test_the_api_over_http(self):
        status, _, body = self.ask("GET", "/api/project", headers=self.bearer())
        self.assertEqual((status, json.loads(body)["main"]), (200, "report.md"))
        status, _, body = self.ask("GET", "/api/file?path=../x", headers=self.bearer())
        self.assertEqual((status, json.loads(body)["code"]), (403, "outside"))


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

    def test_serve_wants_a_folder(self):
        done = self.pdfmd("--serve", "no-such-folder")
        self.assertEqual(done.returncode, 2)
        self.assertIn("is not one", done.stderr)


if __name__ == "__main__":
    unittest.main()
