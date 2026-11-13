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


class CommandMetadataPrecedence(RouteCase):
    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_checkout_cli_metadata_wins_without_stopping_other_appends(self):
        self.source.write_text('---\nauthor+: [Partner]\nkeywords+: [Extra]\n---\nText.\n')
        (self.root / "base.yaml").write_text('author: [Base]\nkeywords: [Original]\n')
        (self.root / "template.html").write_text('$for(author)$$author$$sep$|$endfor$:$for(keywords)$$keywords$$sep$|$endfor$\n')
        for arguments in (("-M", "author=CLI Author"), ("-M", "author:CLI Author"),
                          ("-Mauthor=CLI Author",)):
            with self.subTest(arguments=arguments):
                self.run_pdfmd("--to", "html", "-o", str(self.root / "d.html"), "-y", str(self.root / "base.yaml"),
                               "--standalone", "--template", str(self.root / "template.html"), *arguments)
                self.assertEqual((self.root / "d.html").read_text().strip(), 'CLI Author:Original|Extra')


class CodeMetadataPrecedence(RouteCase):
    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_patch_report_metadata_code_settings_beat_global(self):
        config = self.root / "config.yaml"
        config.write_text('options: {line-numbers: true, report-build: patch}\n')
        self.env["PDFMD_CONFIG"] = str(config)
        metadata = self.root / "base.yaml"
        metadata.write_text('pdfmd-options: {line-numbers: false}\n')
        self.source.write_text('```python\na = 1\n```\n')
        other = self.root / "other.md"
        other.write_text('Text.\n')
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "pdfmd"), "-r", str(self.source), str(other),
                               "--to", "latex", "-o", str(self.root / "report.tex"), "-y", str(metadata),
                               "--no-stamp", "--no-backup"], cwd=self.root, env=self.env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=90)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("numbers=left", (self.root / "report.tex").read_text())

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_checkout_metadata_code_settings_beat_global_and_yield_to_cli_and_document(self):
        config = self.root / "config.yaml"
        config.write_text('options: {line-numbers: true, line-number-step: 5}\n')
        self.env["PDFMD_CONFIG"] = str(config)
        (self.root / "base.yaml").write_text('pdfmd-options: {line-numbers: false, line-number-step: 9}\n')
        for options, arguments, numbered, step in (
                ('{}', (), False, None),
                ('{}', ('--line-numbers', '4'), True, 4),
                ('{line-numbers: true}', (), True, 9)):
            with self.subTest(options=options, arguments=arguments):
                self.source.write_text(f'---\npdfmd-options: {options}\n---\n\n```\na\nb\nc\n```\n')
                self.run_pdfmd("--to", "latex", "-o", str(self.root / "d.tex"),
                               "-y", str(self.root / "base.yaml"), *arguments)
                result = (self.root / "d.tex").read_text()
                self.assertEqual('numbers=left' in result, numbered)
                if step:
                    self.assertIn(f'stepnumber={step}', result)


class FencedMetadataSettings(RouteCase):
    def test_metadata_settings_and_engine_survive_supported_fences(self):
        self.source.write_text('Text.\n')
        metadata = self.root / "base.yaml"
        expected = {"pdfmd-options": {"engine": "typst", "line-numbers": True}}
        for ending in ('---', '...', None):
            with self.subTest(ending=ending):
                body = 'pdfmd-options: {engine: typst, line-numbers: true}\n'
                metadata.write_text(f'---\n{body}{ending}\n' if ending else body)
                self.assertEqual(pdfmd.metadata_file_yaml(metadata), expected)
                self.assertEqual(pdfmd.frontmatter_engine(self.source, [metadata]), 'typst')

    @unittest.skipUnless(shutil.which("pandoc"), "needs Pandoc")
    def test_checkout_fenced_metadata_settings_beat_global_defaults(self):
        self.source.write_text('```\na\nb\nc\n```\n')
        config = self.root / "config.yaml"
        config.write_text('options: {line-numbers: false}\n')
        self.env["PDFMD_CONFIG"] = str(config)
        metadata = self.root / "base.yaml"
        metadata.write_text('---\npdfmd-options: {line-numbers: true, line-number-step: 3}\n---\n')
        self.run_pdfmd('--to', 'latex', '-o', str(self.root / 'd.tex'), '-y', str(metadata))
        text = (self.root / 'd.tex').read_text()
        self.assertIn('numbers=left', text)
        self.assertIn('stepnumber=3', text)


class FontMetadataPrecedence(RouteCase):
    def test_font_lookup_follows_file_priority_document_and_cli(self):
        self.source.write_text('Text.\n')
        base, extra = self.root / 'base.yaml', self.root / 'extra.yaml'
        base.write_text('mainfont: Earlier\n')
        extra.write_text('mainfont: Later\n')
        for precedence, expected in (('later', 'Later'), ('first', 'Earlier')):
            with self.subTest(precedence=precedence), patch.object(pdfmd, 'METADATA_PRECEDENCE_CLI', precedence):
                self.assertEqual(pdfmd.document_font_setting('mainfont', [self.source], [base, extra], []), expected)
        self.source.write_text('---\nmainfont: Document\n---\nText.\n')
        self.assertEqual(pdfmd.document_font_setting('mainfont', [self.source], [base, extra], []), 'Document')
        self.assertEqual(pdfmd.document_font_setting('mainfont', [self.source], [base, extra], ['mainfont=CLI']), 'CLI')

    @unittest.skipUnless(shutil.which('pandoc'), 'needs Pandoc')
    def test_checkout_managed_earlier_font_cannot_override_later_metadata(self):
        self.source.write_text('Text.\n')
        # The managed fonts sit in data_root(): under XDG_DATA_HOME, and under %LOCALAPPDATA% on Windows.
        data = Path(self.env['XDG_DATA_HOME'])
        self.env['LOCALAPPDATA'] = str(data)
        with patch.dict(os.environ, self.env):
            managed = pdfmd.data_root() / 'fonts'
            with patch.object(sys, 'platform', 'win32'):
                self.assertEqual(pdfmd.data_root(), data / 'pdfmd')
        self.assertEqual(managed, data / 'pdfmd' / 'fonts')         # never the real folder
        managed.mkdir(parents=True)
        # Give the shipped test font a private family name, only in this scratch copy.
        font = (ROOT / 'lib' / 'pdfmd_inkmd' / 'assets' / 'fonts' / 'DejaVuSans.ttf').read_bytes()
        for encoding in ('utf-16-be', 'ascii'):
            font = font.replace('DejaVu Sans'.encode(encoding), 'PdfmdX Sans'.encode(encoding))
        (managed / 'Earlier.ttf').write_bytes(font)
        base, extra = self.root / 'base.yaml', self.root / 'extra.yaml'
        base.write_text('mainfont: PdfmdX Sans\n')
        extra.write_text('mainfont: DejaVu Serif\n')
        for precedence in ('later', 'first'):
            with self.subTest(precedence=precedence):
                self.run_pdfmd('--to', 'latex', '-o', str(self.root / 'd.tex'), '-y', str(base), str(extra),
                               '--metadata-precedence', precedence, '--no-auto', 'unicode')
                text = (self.root / 'd.tex').read_text()
                if precedence == 'later':
                    self.assertIn('\\setmainfont[]{DejaVu Serif}', text)
                    self.assertNotIn('Earlier.ttf', text)
                else:
                    self.assertIn('Earlier.ttf', text)


class DotsFrontMatter(RouteCase):
    def document(self, ending='...', newline='\n'):
        text = ('---\nmainfont: DejaVu Serif\nmonofont: DejaVu Sans Mono\nmargin: 2cm\n'
                + ending + '\n\nBody.\n\nmargin: 9cm\n')
        self.source.write_text(text.replace('\n', newline))
        return text.replace('\n', newline)

    def test_font_detection_accepts_both_end_markers(self):
        for ending in ('---', '...'):
            with self.subTest(ending=ending):
                self.document(ending)
                self.assertTrue(pdfmd.has_mainfont(self.source, []))
                self.assertTrue(pdfmd.has_monofont(self.source, []))

    def test_margin_detection_and_latex_translation_accept_both_end_markers(self):
        for ending in ('---', '...'):
            with self.subTest(ending=ending):
                self.document(ending)
                self.assertTrue(pdfmd.has_geometry(self.source, []))
                self.assertEqual(pdfmd.frontmatter_margin_geometry_options(self.source, []), ['margin=2cm'])

    def test_typst_conversion_preserves_the_end_marker_and_body(self):
        for ending in ('---', '...'):
            with self.subTest(ending=ending):
                text = self.document(ending)
                fixed = pdfmd.fix_typst_margin(text)
                self.assertEqual(pdfmd.front_matter_dict(fixed)['margin'], {'x': '2cm', 'y': '2cm'})
                self.assertTrue(fixed.endswith(ending + '\n\nBody.\n\nmargin: 9cm\n'))

    def test_crlf_front_matter_keeps_margin_and_body(self):
        for ending in ('---', '...'):
            with self.subTest(ending=ending):
                fixed = pdfmd.fix_typst_margin(self.document(ending, '\r\n'))
                self.assertEqual(pdfmd.front_matter_dict(fixed)['margin'], {'x': '2cm', 'y': '2cm'})
                self.assertTrue(fixed.endswith(ending + '\r\n\r\nBody.\r\n\r\nmargin: 9cm\r\n'))

    def test_detection_and_scalar_translation_work_without_yaml(self):
        self.document()
        with patch.object(pdfmd, 'yaml', None):
            self.assertTrue(pdfmd.has_mainfont(self.source, []))
            self.assertTrue(pdfmd.has_geometry(self.source, []))
            self.assertEqual(pdfmd.frontmatter_margin_geometry_options(self.source, []), ['margin=2cm'])
            self.assertIn('  x: 2cm\n  y: 2cm', pdfmd.fix_typst_margin(self.source.read_text()))

    @unittest.skipUnless(shutil.which('pandoc'), 'needs Pandoc')
    def test_checkout_latex_and_typst_keep_document_fonts_and_margins(self):
        self.document()
        self.run_pdfmd('--to', 'latex', '-o', str(self.root / 'd.tex'), '--no-auto', 'unicode')
        text = (self.root / 'd.tex').read_text()
        self.assertIn('\\setmainfont[]{DejaVu Serif}', text)
        self.assertIn('\\setmonofont[]{DejaVu Sans Mono}', text)
        self.assertIn('\\usepackage[margin=2cm]{geometry}', text)
        self.run_pdfmd('--to', 'typst', '--standalone', '-o', str(self.root / 'd.typ'), '--no-auto', 'unicode')
        text = (self.root / 'd.typ').read_text()
        self.assertRegex(text, r'margin:\s*\([^)]*x:\s*2cm[^)]*y:\s*2cm')
