"""Install ownership and the opt-in version notice, using local receipts and fake PyPI replies."""

from __future__ import annotations

import contextlib
import importlib.metadata
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/, for isolation_support
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402


class Upgrade(unittest.TestCase):
    def guidance(self, home, module, prefix, dist):
        from pdfmd_install.provenance import upgrade_command

        with mock.patch.object(pdfmd, "__file__", str(module)), mock.patch.object(sys, "prefix", str(prefix)), \
                mock.patch.object(pdfmd, "cache_root", return_value=home / "cache"), \
                mock.patch.object(importlib.metadata, "distribution", return_value=dist), \
                mock.patch.object(pdfmd, "open_url", side_effect=AssertionError("network access")), \
                mock.patch.object(subprocess, "Popen", side_effect=AssertionError("subprocess started")), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            upgrade_command()
        return out.getvalue()

    def test_checkout_command_prints_guidance_and_records_its_source(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "--upgrade"], cwd=home,
                                  capture_output=True, text=True, encoding="utf-8",
                                  env={**os.environ, "PATH": "", "XDG_CACHE_HOME": directory, "LOCALAPPDATA": directory})
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("Install source: checkout", done.stdout)
            records = list((home / "pdfmd" / "install-sources").glob("*.json"))
            self.assertEqual(len(records), 1)
            self.assertEqual(json.loads(records[0].read_text(encoding="utf-8")),
                             {"source": "checkout", "version": pdfmd.PDFMD_VERSION})

    def test_receipts_identify_the_running_install_without_running_a_manager(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            brew = home / "Cellar" / "pdfmd" / "release" / "libexec"
            scoop = home / "apps" / "pdfmd" / "release" / "venv"
            pipx = home / "pipx" / "venvs" / "pdfmd-cli-test"

            def fixture(path, data):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data), encoding="utf-8")

            fixture(brew.parent / "INSTALL_RECEIPT.json", {"source": {"path": "Formula/pdfmd.rb"}})
            fixture(scoop.parent / "install.json", {"bucket": "pdfmd"})
            fixture(scoop.parent / "manifest.json", {"bin": r"venv\Scripts\pdfmd.exe"})
            fixture(pipx / "pipx_metadata.json", {"main_package": {"package": "pdfmd-cli", "suffix": "-test"}})

            ordinary = home / "venvs" / "ordinary"
            for prefix, installer, command in (
                (ordinary, "pip", "python -m pip install --upgrade pdfmd-cli"),
                (pipx, "pip", "pipx upgrade pdfmd-cli-test"),
                (brew, "pip", "brew upgrade pdfmd"),
                (scoop, "pip", "scoop update pdfmd"),
                (home / "other", "uv", "Install source unknown"),
            ):
                with self.subTest(prefix=prefix.name):
                    site = prefix / "site-packages"
                    module = site / "pdfmd.py"
                    dist_info = site / "pdfmd_cli-test.dist-info"
                    dist_info.mkdir(parents=True)
                    module.touch()
                    (dist_info / "INSTALLER").write_text(installer, encoding="utf-8")
                    (dist_info / "RECORD").write_text("pdfmd.py,,\n", encoding="utf-8")
                    dist = importlib.metadata.PathDistribution(dist_info)
                    out = self.guidance(home, module, prefix, dist)
                    self.assertIn(command, out)
                    if command == "Install source unknown":
                        for option in ("pipx upgrade pdfmd-cli", "python -m pip install --upgrade pdfmd-cli",
                                       "brew upgrade pdfmd", "scoop update pdfmd"):
                            self.assertIn(option, out)
                    else:
                        self.assertNotIn("Install source unknown", out)
                    if prefix == scoop:
                        with mock.patch.dict(os.environ, {"SCOOP_GLOBAL": str(home)}):
                            self.assertIn("scoop update pdfmd --global", self.guidance(home, module, prefix, dist))

            other_copy = home / "unrelated" / "pdfmd.py"
            other_copy.parent.mkdir()
            other_copy.touch()
            dist = importlib.metadata.PathDistribution(ordinary / "site-packages" / "pdfmd_cli-test.dist-info")
            self.assertIn("Install source unknown", self.guidance(home, other_copy, ordinary, dist))

            for receipt, prefix in (
                (scoop.parent / "install.json", scoop),
                (brew.parent / "INSTALL_RECEIPT.json", brew),
                (pipx / "pipx_metadata.json", pipx),
            ):
                with self.subTest(prefix=prefix.name):
                    site = prefix / "site-packages"
                    dist = importlib.metadata.PathDistribution(site / "pdfmd_cli-test.dist-info")
                    receipt.write_text("broken receipt", encoding="utf-8")
                    self.assertIn("Install source unknown", self.guidance(home, site / "pdfmd.py", prefix, dist))
                    receipt.unlink()
                    self.assertIn("Install source unknown", self.guidance(home, site / "pdfmd.py", prefix, dist))


class VersionNotice(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache = Path(directory.name)
        self.config = self.cache / "config.yaml"
        self.newer = self.bump(1)

    @staticmethod
    def bump(delta):
        family, _, patch = pdfmd.PDFMD_VERSION.rpartition(".")
        return f"{family}.{int(patch) + delta}"

    def version(self, config=""):
        self.config.write_text(config, encoding="utf-8")
        pdfmd.load_config.cache_clear()
        try:
            with mock.patch.dict(os.environ, {"PDFMD_CONFIG": str(self.config)}), \
                    mock.patch.object(sys, "argv", ["pdfmd", "--version"]), \
                    mock.patch.object(pdfmd, "cache_root", return_value=self.cache), \
                    contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit) as exit_status:
                    pdfmd.main()
                self.assertEqual(exit_status.exception.code, 0)
                self.assertEqual(out.getvalue(), f"pdfmd {pdfmd.PDFMD_VERSION}\n")
                return err.getvalue()
        finally:
            pdfmd.load_config.cache_clear()

    @staticmethod
    def response(version):
        return io.BytesIO(json.dumps({"info": {"version": version}}).encode("utf-8"))

    def test_version_notice_is_off_by_default_and_can_be_disabled_again(self):
        with mock.patch.object(pdfmd, "open_url", return_value=self.response(self.newer)) as request:
            self.assertEqual(self.version(), "")
            request.assert_not_called()
            self.assertIn(self.newer, self.version("options: {version-check: on}"))
            self.assertEqual(self.version("options: {version-check: off}"), "")
            request.assert_called_once()

    def test_fresh_cache_and_configured_expiry(self):
        enabled = "options: {version-check: on}"
        with mock.patch.object(pdfmd, "open_url", return_value=self.response(self.newer)) as request:
            self.assertIn(self.newer, self.version(enabled))
        self.assertEqual(request.call_args.args[0].full_url, "https://pypi.org/pypi/pdfmd-cli/json")
        record, = self.cache.glob("*.json")
        checked = record.stat().st_mtime
        older = checked - 23 * 3600
        os.utime(record, (older, older))
        with mock.patch.object(pdfmd, "open_url", return_value=self.response(pdfmd.PDFMD_VERSION)) as request:
            self.assertIn(self.newer, self.version(enabled))
            request.assert_not_called()
            self.assertEqual(self.version("options: {version-check: on, version-check-cache-hours: 1}"), "")
            request.assert_called_once()
            self.assertEqual(self.version(enabled), "")
            request.assert_called_once()

    def test_the_default_cache_expires_after_a_day_and_a_damaged_cache_is_refreshed(self):
        enabled = "options: {version-check: on}"
        with mock.patch.object(pdfmd, "open_url", return_value=self.response(self.newer)):
            self.assertIn(self.newer, self.version(enabled))
        record, = self.cache.glob("*.json")
        older = record.stat().st_mtime - 25 * 3600
        os.utime(record, (older, older))
        with mock.patch.object(pdfmd, "open_url", return_value=self.response(self.newer)) as request:
            self.assertIn(self.newer, self.version(enabled))
            request.assert_called_once()
        record.write_text("broken cache", encoding="utf-8")
        with mock.patch.object(pdfmd, "open_url", return_value=self.response(self.newer)) as request:
            self.assertIn(self.newer, self.version(enabled))
            request.assert_called_once()

    def test_an_unwritable_cache_does_not_hide_the_notice(self):
        (self.cache / "pypi-version.json").mkdir()
        with mock.patch.object(pdfmd, "open_url", return_value=self.response(self.newer)):
            self.assertIn(self.newer, self.version("options: {version-check: on}"))

    def test_offline_invalid_and_older_releases_leave_version_output_alone(self):
        enabled = "options: {version-check: true}"
        for reply in (OSError("offline"), io.BytesIO(b"not JSON"), self.response({}), self.response(f"{self.newer}rc1"),
                      self.response(self.bump(-1))):
            with self.subTest(reply=reply), mock.patch.object(pdfmd, "open_url", side_effect=[reply]) as request:
                self.assertEqual(self.version(enabled), "")
                request.assert_called_once()
