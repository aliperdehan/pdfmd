"""Installation and reuse of pinned styles with HTTP replaced by fixtures."""
from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402

TEMPLATE = b"<!-- SPDX-License-Identifier: MIT -->\n<main>Fixture $body$</main>\n"
CSL = ('<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text">'
       '<info><title>Fixture</title><id>https://example.invalid/sample</id>'
       '<rights license="https://creativecommons.org/licenses/by-sa/3.0/">CC BY-SA</rights></info>'
       '<citation><layout prefix="FIXTURE "><text variable="title"/></layout></citation>'
       '<bibliography><layout><text variable="title"/></layout></bibliography></style>')
REPO = "example/templates"
REVISION = "a" * 40
TREE = "b" * 40


class InstalledStyles(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        config, cache = self.root / "config", self.root / "cache"
        self.environment = {**os.environ, "XDG_CONFIG_HOME": str(config), "XDG_CACHE_HOME": str(cache),
                            "APPDATA": str(config), "LOCALAPPDATA": str(cache), "PDFMD_NO_PROMPT": "1"}
        env = mock.patch.dict(os.environ, self.environment)
        env.start()
        self.addCleanup(env.stop)
        network = mock.patch.object(pdfmd, "open_url", side_effect=AssertionError("unexpected HTTP request"))
        network.start()
        self.addCleanup(network.stop)

    def install(self, source, assume_yes=True):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            result = pdfmd.install_extra(source, assume_yes)
        return result, out.getvalue()

    def build(self, text, *options):
        document, output = self.root / "sample.md", self.root / "result.html"
        document.write_text(text, encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), str(document),
                               "--to", "html", "-o", str(output), "--no-stamp", "--no-backup", *options],
                              cwd=self.root, env=self.environment, capture_output=True, encoding="utf-8", timeout=120)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return output.read_text(encoding="utf-8")

    def test_install_arguments_are_explicit(self):
        self.assertEqual(pdfmd.install_kind("template:fixture"), "template:fixture")
        self.assertEqual(pdfmd.install_kind("csl:fixture"), "csl:fixture")

    def test_repository_requires_an_asset_path_and_records_its_commit(self):
        from pdfmd_install import styles

        api = f"{styles.GITHUB_API}/{REPO}"
        tree_url = f"{api}/git/trees/{TREE}?recursive=1"
        raw = f"{styles.GITHUB_RAW}/{REPO}/{REVISION}/assets/example.html5"
        entries = {
            styles.TEMPLATE_INDEX: {"content": base64.b64encode(json.dumps(
                [{"id": "fixture", "github_repository": f"https://github.com/{REPO}"}]).encode()).decode()},
            api: {"default_branch": "main", "license": {"spdx_id": "MIT"}},
            f"{api}/commits/main": {"sha": REVISION, "commit": {"tree": {"sha": TREE}}},
            tree_url: {"tree": [{"type": "blob", "path": "assets/example.html5"},
                                {"type": "blob", "path": "assets/example.latex"}]},
        }
        responses = {url: json.dumps(data).encode() for url, data in entries.items()} | {raw: TEMPLATE}
        with mock.patch.object(styles, "download", side_effect=responses.__getitem__) as fetch:
            good, log = self.install("template:fixture")
            self.assertFalse(good)
            self.assertIn("several assets match; specify #ASSET-PATH", log)
            self.assertNotIn(mock.call(raw), fetch.call_args_list)
            good, log = self.install("template:fixture#assets/example.html5", assume_yes=False)
            self.assertFalse(good)
            self.assertIn("Licence: MIT", log)
            self.assertIn("add --yes", log)
            self.assertFalse(list(self.root.rglob("asset.json")))
            good, log = self.install("template:fixture#assets/example.html5")
        self.assertTrue(good, log)
        self.assertIn(f"Source: {raw}", log)
        self.assertIn(f"Revision: {REVISION}", log)
        self.assertIn("Licence: MIT", log)
        [record] = self.root.rglob("asset.json")
        saved = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual(saved["sha256"], hashlib.sha256(TEMPLATE).hexdigest())

    def test_direct_template_requires_a_licence_and_records_the_digest(self):
        from pdfmd_install import styles

        source = "template:https://example.invalid/template.html5"
        with mock.patch.object(styles, "download", return_value=b"$body$"):
            good, log = self.install(source)
        self.assertFalse(good)
        self.assertIn("cannot identify the licence", log)
        self.assertFalse(list(self.root.rglob("asset.json")))
        with mock.patch.object(styles, "download", return_value=TEMPLATE):
            good, log = self.install(source)
        self.assertTrue(good, log)
        self.assertIn("Revision: sha256:" + hashlib.sha256(TEMPLATE).hexdigest(), log)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_pinned_template_lookup_and_explicit_refresh(self):
        from pdfmd_install import styles

        name = "example/templates#assets/example.html5"
        with mock.patch.object(styles, "from_repository", return_value=styles.Asset(
                "example.html5", "https://example.invalid/template.html5", REVISION, "MIT", TEMPLATE)):
            self.assertTrue(self.install(f"template:{name}")[0])
        self.assertIn("<main>Fixture", self.build("Text.\n", f"--template={name}"))
        self.assertIn("<main>Fixture", self.build(f"---\npdfmd-options: {{template: {name}}}\n---\nText.\n"))
        with mock.patch.object(styles, "from_repository", return_value=styles.Asset(
                "example.html5", "https://example.invalid/template.html5", TREE, "MIT", TEMPLATE.replace(b"Fixture", b"Refreshed"))):
            self.assertTrue(self.install(f"template:{name}")[0])
        self.assertIn("<main>Refreshed", self.build("Text.\n", "--template", name))
        with mock.patch.object(styles, "from_repository", side_effect=OSError("offline")):
            self.assertFalse(self.install(f"template:{name}")[0])
        self.assertIn("<main>Refreshed", self.build("Text.\n", "--template", name))

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_pinned_csl_uses_the_cache_without_rolling_refresh(self):
        from pdfmd_config.installed_styles import pinned_style

        from pdfmd_install import styles

        name = "https://example.invalid/fixture"
        with mock.patch.object(pdfmd, "fetch_csl", return_value=(CSL, "")) as fetch:
            self.assertTrue(self.install(f"csl:{name}")[0])
            fetch.assert_called_once_with(name)
        local = pinned_style("csl", name)
        self.assertIsNotNone(local)
        old = time.time() - 60 * 86400
        os.utime(local, (old, old))
        with mock.patch.object(pdfmd, "fetch_csl", side_effect=AssertionError("pinned CSL was fetched")):
            self.assertEqual(pdfmd.remote_csl(name, self.root / "sample.md", []), local)
        api = f"{styles.GITHUB_API}/{styles.CSL_REPOSITORY}"
        tree = f"{api}/git/trees/{TREE}?recursive=1"
        entries = {api: {"default_branch": "master"},
                   f"{api}/commits/master": {"sha": REVISION, "commit": {"tree": {"sha": TREE}}},
                   tree: {"tree": [{"type": "blob", "path": "other.csl"},
                                   {"type": "blob", "path": "dependent/fixture.csl"}]}}
        with (mock.patch.object(styles, "json_response", side_effect=entries.__getitem__),
              mock.patch.object(pdfmd, "fetch_csl", return_value=(CSL, "")) as fetch):
            self.assertTrue(self.install("csl:fixture")[0])
            fetch.assert_called_once_with(
                f"{styles.GITHUB_RAW}/{styles.CSL_REPOSITORY}/{REVISION}/dependent/fixture.csl")
        name = "fixture"
        document = "---\nreferences:\n- {id: book, type: book, title: A Book}\n"
        output = self.build(document + f"csl: {name}\n---\n\nSee [@book].\n")
        self.assertIn("FIXTURE A Book", " ".join(output.split()))
        output = self.build(document + "---\n\nSee [@book].\n", f"--csl={name}")
        self.assertIn("FIXTURE A Book", " ".join(output.split()))
        (self.root / "fixture.csl").write_text(CSL.replace("FIXTURE", "LOCAL"), encoding="utf-8")
        output = self.build(document + "---\n\nSee [@book].\n", f"--csl={name}")
        self.assertIn("LOCAL A Book", " ".join(output.split()))
