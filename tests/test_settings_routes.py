"""Regressions for settings precedence and helper-build routes."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd  # noqa: E402


class RouteCase(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="pdfmd-settings-routes-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.source = self.root / "d.md"
        self.env = {**os.environ, "PDFMD_CONFIG": "", "PDFMD_NO_PROMPT": "1",
                    "XDG_CONFIG_HOME": str(self.root / "config"), "XDG_CACHE_HOME": str(self.root / "cache"),
                    "XDG_DATA_HOME": str(self.root / "data")}
        self.environment = patch.dict(os.environ, self.env)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def run_pdfmd(self, *args):
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), str(self.source),
                               "--no-stamp", "--no-backup", "--rewrite", *args], cwd=self.root, env=self.env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=90)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done


class ReferenceNumberRoutes(RouteCase):
    def test_helper_forces_latex_and_disables_nested_collection(self):
        self.source.write_text('---\npdfmd-options: {engine: typst, office: {latex: auto}}\n---\nSee \\ref{x}.\n')
        with patch.object(pdfmd, "installed_engines", return_value=["typst", "lualatex"]), \
                patch.object(pdfmd, "kpsewhich_locate", return_value={}), \
                patch.object(pdfmd.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)) as run:
            pdfmd.office_label_data(self.source, [], [], ["officeref"], lambda *a: None, self.root, "auto")
        command = run.call_args.args[0]
        self.assertIn("-e", command)
        self.assertEqual(command[command.index("-e") + 1], "lualatex")
        self.assertIn("officelatex", command)

    def test_no_suitable_engine_does_not_launch_a_child(self):
        self.source.write_text('See \\ref{x}.\n')
        with patch.object(pdfmd, "installed_engines", return_value=["typst", "context"]), \
                patch.object(pdfmd, "kpsewhich_locate", return_value={}), \
                patch.object(pdfmd.subprocess, "run") as run:
            pdfmd.office_label_data(self.source, [], [], None, lambda *a: None, self.root, "auto")
        run.assert_not_called()

    @unittest.skipUnless(shutil.which("pandoc") and shutil.which("lualatex"), "needs Pandoc and LuaLaTeX")
    def test_checkout_html_with_typst_document_setting_finishes(self):
        self.source.write_text('---\npdfmd-options: {engine: typst, office: {latex: auto}}\n---\n'
                               '\\begin{equation}a=1\\label{x}\\end{equation}\n\nSee \\ref{x}.\n')
        self.run_pdfmd("--to", "html", "-o", str(self.root / "d.html"))
        self.assertIn('class="pdfmd-ref">1</a>', (self.root / "d.html").read_text())


class AutoAliasPrecedence(RouteCase):
    def test_resolved_states_contain_only_concrete_kinds(self):
        for lower in ({"no-auto": ["files"]}, {"no-auto": True}, {"auto": {"files": "explicit-only"}}):
            with self.subTest(lower=lower):
                result = pdfmd.resolve_auto([("document", {"auto": {"lua": "on"}}), ("config", lower)])
                self.assertFalse(pdfmd.auto_disabled(result, "lua"), result)
                self.assertFalse(pdfmd.discovery_disabled(result, "lua"), result)
                self.assertFalse(set(result or []) & set(pdfmd.NO_AUTO_ALIASES), result)
                self.assertNotIn("explicit:files", result or [])
                self.assertTrue(pdfmd.discovery_disabled(result, "preamble"), result)

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_checkout_document_reenables_lua_under_disabled_files(self):
        config = self.root / "config.yaml"
        config.write_text('options: {no-auto: [files]}\n')
        self.env["PDFMD_CONFIG"] = str(config)
        self.source.write_text('---\npdfmd-options: {auto: {lua: on}}\n---\nTOKEN\n')
        (self.root / "d.lua").write_text('function Str(el) if el.text == "TOKEN" then return pandoc.Str("RESTORED") end end\n')
        self.run_pdfmd("--to", "html", "-o", str(self.root / "d.html"))
        self.assertIn("RESTORED", (self.root / "d.html").read_text())
