"""Named filters and preambles follow option layers and their owning files."""
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
import pdfmd


class NamedFiles(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.doc = self.root / 'doc.md'
        self.doc.write_text('Original\n')
        self.env = {**os.environ, 'PDFMD_CONFIG': '', 'PDFMD_NO_PROMPT': '1',
                    **{'XDG_' + key + '_HOME': str(self.root / key.lower()) for key in ('CONFIG', 'CACHE', 'DATA')}}

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def assets(self, folder, before='Original', after='Changed'):
        self.write(folder + '/change.lua',
                   'function Str(s) if s.text == "' + before + '" then s.text = "' + after + '" end return s end\n')
        self.write(folder + '/extra.tex', '\\newcommand{\\Named' + after + '}{yes}\n')

    def build(self, target, *args, ok=True):
        if not shutil.which('pandoc'):
            self.skipTest('needs Pandoc')
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/pdfmd'), 'doc.md', '--to', target,
                               '--no-backup', '--no-stamp', '--no-auto', 'font', *args], cwd=self.root,
                              env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        if ok:
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        else:
            self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        return done

    def text(self, target):
        return (self.root / ('doc.html' if target == 'html' else 'doc.tex')).read_text()

    def test_metadata_paths_and_trust_note(self):
        self.assets('meta/assets')
        self.write('meta/settings.yaml', 'pdfmd-options:\n  lua-filter: assets/change.lua\n  preamble: assets/extra.tex\n')
        done = self.build('html', '-y', 'meta/settings.yaml')
        self.assertIn('Changed', self.text('html'))
        self.assertIn('is new here; it runs', done.stdout)
        self.build('latex', '-y', 'meta/settings.yaml')
        self.assertIn('\\NamedChanged', self.text('latex'))

    def test_folder_layer_paths(self):
        self.assets('.pdfmd/assets')
        self.write('.pdfmd/config.yaml', 'inherit: false\noptions:\n  lua-filter: assets/change.lua\n  preamble: assets/extra.tex\n')
        self.build('html')
        self.assertIn('Changed', self.text('html'))
        self.build('latex')
        self.assertIn('\\NamedChanged', self.text('latex'))

    def test_document_paths_still_work(self):
        self.assets('own')
        self.doc.write_text('---\npdfmd-options: {lua-filter: own/change.lua, preamble: own/extra.tex}\n---\nOriginal\n')
        self.build('html')
        self.assertIn('Changed', self.text('html'))
        self.build('latex')
        self.assertIn('\\NamedChanged', self.text('latex'))

    def test_append_keeps_both_origins(self):
        self.assets('meta/assets', after='First')
        self.assets('own', before='First', after='Final')
        self.write('meta/settings.yaml', 'pdfmd-options:\n  lua-filter: assets/change.lua\n  preamble: assets/extra.tex\n')
        for suffix in ('+', '+='):
            with self.subTest(suffix=suffix):
                self.doc.write_text('---\npdfmd-options:\n  lua-filter' + suffix + ': own/change.lua\n  preamble' + suffix + ': own/extra.tex\n---\nOriginal\n')
                self.build('html', '-y', 'meta/settings.yaml')
                self.assertIn('Final', self.text('html'))
                self.build('latex', '-y', 'meta/settings.yaml')
                self.assertIn('\\NamedFirst', self.text('latex'))
                self.assertIn('\\NamedFinal', self.text('latex'))

    def test_nearest_list_replaces(self):
        self.assets('own')
        self.doc.write_text('---\npdfmd-options: {lua-filter: [own/change.lua], preamble: [own/extra.tex]}\n---\nOriginal\n')
        self.write('meta/settings.yaml', 'pdfmd-options: {lua-filter: missing.lua, preamble: missing.tex}\n')
        self.build('html', '-y', 'meta/settings.yaml')
        self.assertIn('Changed', self.text('html'))
        self.build('latex', '-y', 'meta/settings.yaml')
        self.assertIn('\\NamedChanged', self.text('latex'))

    def test_missing_named_metadata_files_are_errors(self):
        for kind, target, name in (('lua-filter', 'html', 'missing.lua'), ('preamble', 'latex', 'missing.tex')):
            with self.subTest(kind=kind):
                self.write('meta/settings.yaml', 'pdfmd-options: {' + kind + ': ' + name + '}\n')
                done = self.build(target, '-y', 'meta/settings.yaml', ok=False)
                self.assertIn("which doesn't exist", done.stdout + done.stderr)
                self.assertIn(name, done.stdout + done.stderr)

    def test_global_setup_paths(self):
        self.assets('global/assets')
        config = self.write('global/config.yaml', 'options: {lua-filter: assets/change.lua, preamble: assets/extra.tex}\n')
        with patch.object(pdfmd, 'config_path', return_value=config):
            pdfmd.load_config.cache_clear()
            try:
                self.assertEqual(pdfmd.frontmatter_extra_lua_filters(self.doc), [(config.parent / 'assets/change.lua').resolve()])
                self.assertEqual(pdfmd.frontmatter_extra_preambles(self.doc), [(config.parent / 'assets/extra.tex').resolve()])
            finally:
                pdfmd.load_config.cache_clear()

    def test_strict_checks_a_folder_filter(self):
        self.assets('.pdfmd/assets')
        self.write('.pdfmd/config.yaml', 'inherit: false\noptions: {lua-filter: assets/change.lua}\n')
        done = self.build('html', '--strict', ok=False)
        self.assertIn('was not run (--strict)', done.stdout + done.stderr)
        self.assertIn('Original', self.text('html'))
        self.assertNotIn('Changed', self.text('html'))

    def test_apply_checks_a_metadata_filter_and_clears_embedded_append_names(self):
        if not shutil.which('pandoc'):
            self.skipTest('needs Pandoc')
        self.assets('meta/assets', after='First')
        self.assets('own', before='First', after='Final')
        self.write('meta/settings.yaml', 'pdfmd-options: {lua-filter: assets/change.lua, preamble: assets/extra.tex}\n')
        self.doc.write_text('---\npdfmd-options: {lua-filter+: own/change.lua, preamble+: own/extra.tex}\n---\nOriginal\n')
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/pdfmd'), 'doc.md', '--assemble-only',
                               '--embed-metadata', '--lua-mode', 'apply', '-y', 'meta/settings.yaml',
                               '--no-backup', '--no-stamp', '-o', 'combined.md'], cwd=self.root, env=self.env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('is new here; it runs', done.stdout)
        text = (self.root / 'combined.md').read_text()
        self.assertIn('Final', text)
        options = pdfmd.frontmatter_pdfmd_options(self.root / 'combined.md')
        self.assertNotIn('lua-filter+', options)
        self.assertNotIn('preamble+', options)
        self.assertIn('\\NamedFirst', text)
        self.assertIn('\\NamedFinal', text)

    def test_batch_passes_actual_metadata_to_preamble_resolution(self):
        if not shutil.which('pandoc'):
            self.skipTest('needs Pandoc')
        self.assets('meta/assets')
        self.write('other.md', 'Other\n')
        self.write('meta/settings.yaml', 'pdfmd-options: {preamble: assets/extra.tex}\n')
        for jobs in ('1', '2'):
            with self.subTest(jobs=jobs):
                done = subprocess.run([sys.executable, str(ROOT / 'scripts/pdfmd'), '-b', 'doc.md', 'other.md',
                                       '--to', 'latex', '-j', jobs, '-y', 'meta/settings.yaml', '--no-auto', 'font',
                                       '--no-backup', '--no-stamp'], cwd=self.root, env=self.env,
                                      stdin=subprocess.DEVNULL, capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                for name in ('doc.tex', 'other.tex'):
                    self.assertIn('\\NamedChanged', (self.root / name).read_text())

    def test_both_report_routes_pass_actual_metadata_to_preamble_resolution(self):
        if not shutil.which('pandoc'):
            self.skipTest('needs Pandoc')
        self.assets('meta/assets')
        self.write('other.md', 'Other\n')
        self.write('meta/settings.yaml', 'pdfmd-options: {preamble: assets/extra.tex}\n')
        for route in ('route', 'patch'):
            with self.subTest(route=route):
                self.doc.write_text('---\npdfmd-options: {report-build: ' + route + '}\n---\nOriginal\n')
                done = subprocess.run([sys.executable, str(ROOT / 'scripts/pdfmd'), '-r', 'doc.md', 'other.md',
                                       '--to', 'latex', '-y', 'meta/settings.yaml',
                                       '--no-auto', 'font', '--no-backup', '--no-stamp', '-o', 'book.tex'],
                                      cwd=self.root, env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertIn('\\NamedChanged', (self.root / 'book.tex').read_text())

    def test_grouped_folder_metadata_names(self):
        self.assets('.pdfmd/assets')
        self.write('.pdfmd/config.yaml', 'inherit: false\n')
        self.write('.pdfmd/metadata.yaml', 'pdfmd-options:\n  metadata: {lua: assets/change.lua, preamble: assets/extra.tex}\n')
        self.build('html')
        self.assertIn('Changed', self.text('html'))
        self.build('latex')
        self.assertIn('\\NamedChanged', self.text('latex'))
