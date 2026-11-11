"""HTML maths defaults and explicit choices."""
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


class MathChoice(unittest.TestCase):
    def test_default_and_explicit_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            doc = Path(directory) / 'doc.md'
            doc.write_text('$x$\n')
            for settings, options, expected in (({}, [], ['MATH:mathml']),
                    ({'math': 'katex'}, [], ['MATH:katex']),
                    ({'math': 'mathjax'}, ['--katex'], []),
                    *[({}, [flag], []) for flag in pdfmd.HTML_MATH_OPTIONS]):
                with self.subTest(settings=settings, options=options), \
                     patch.object(pdfmd, 'html_settings', return_value=settings), \
                     patch.object(pdfmd, 'html_math_args', side_effect=lambda m: ['MATH:' + m]):
                    self.assertEqual(pdfmd.html_pandoc_args(doc, [], options, None, lambda *a: None), expected)

    def test_defaults_file_choice_is_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            defaults = Path(directory) / 'chosen.yaml'
            defaults.write_text('html-math-method: katex\n')
            doc = Path(directory) / 'doc.md'
            doc.write_text('$x$\n')
            for options in (['--defaults', str(defaults)], ['--defaults=' + str(defaults)], ['-d' + str(defaults)]):
                with self.subTest(options=options), patch.object(pdfmd, 'html_settings', return_value={}):
                    self.assertEqual(pdfmd.html_pandoc_args(doc, [], options, True, lambda *a: None)[-2:],
                                     ['--metadata', 'pagetitle=doc'])
                    self.assertFalse(any('math' in arg for arg in pdfmd.html_pandoc_args(
                        doc, [], options, True, lambda *a: None)))

    @unittest.skipUnless(shutil.which('pandoc'), 'needs Pandoc')
    def test_fragment_through_pdfmd(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'doc.md').write_text('$x$\n')
            env = {**os.environ, 'PDFMD_CONFIG': '', 'PDFMD_NO_PROMPT': '1',
                   **{'XDG_' + key + '_HOME': str(folder / key.lower()) for key in ('CONFIG', 'CACHE', 'DATA')}}
            done = subprocess.run([sys.executable, str(ROOT / 'scripts/pdfmd'), 'doc.md', '--to', 'html',
                                   '--verbose', '--no-backup'], cwd=folder, env=env, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn('<math', (folder / 'doc.html').read_text())
            self.assertNotIn('<html', (folder / 'doc.html').read_text())
            self.assertTrue(any(arg in done.stdout + done.stderr for arg in pdfmd.html_math_args('mathml')))
