"""The private, generated pure-Python YAML copy and its offline regeneration."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'lib'))


class Vendor(unittest.TestCase):
    def test_private_copy_round_trips_yaml_without_c_extensions_or_shadowing(self):
        code = '''import sys
sys.path.insert(0, sys.argv[1])
import pdfmd_yaml as yaml
assert yaml.__version__ == '6.0.3'
assert not yaml.__with_libyaml__
assert 'yaml' not in sys.modules
assert not any(n.startswith(('pdfmd_yaml.cyaml', 'pdfmd_yaml._yaml', 'yaml.')) for n in sys.modules)
data = yaml.safe_load('base: &x [one, two]\\ncopy: *x\\ntext: |\\n  hello\\n  world\\n')
assert data['base'] is data['copy']
assert data['text'] == 'hello\\nworld\\n'
assert yaml.safe_load(yaml.safe_dump(data)) == data
'''
        done = subprocess.run([sys.executable, '-S', '-c', code, str(ROOT / 'lib')], env={**os.environ},
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_generator_matches_installed_source_and_detects_drift(self):
        try:
            from importlib.metadata import version
            if version('pyyaml') != '6.0.3':
                self.skipTest('regeneration needs installed PyYAML 6.0.3')
        except ImportError:
            self.skipTest('regeneration needs installed PyYAML')
        spec = importlib.util.spec_from_file_location('vendor_pyyaml', ROOT / 'scripts' / 'vendor_pyyaml.py')
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        with mock.patch.object(sys, 'argv', ['vendor_pyyaml', '--check']):
            self.assertEqual(generator.main(), 0)
            with tempfile.TemporaryDirectory(prefix='pdfmd-yaml-drift-') as folder:
                target = Path(folder)
                for name, data in generator.build('6.0.3').items():
                    (target / name).write_bytes(data)
                (target / 'reader.py').write_text('# changed\n', encoding='utf-8')
                with mock.patch.object(generator, 'TARGET', target):
                    self.assertEqual(generator.main(), 1)

    def test_licence_and_provenance_are_shipped(self):
        import pdfmd_yaml
        package = Path(pdfmd_yaml.__file__).parent
        self.assertIn('Permission is hereby granted', (package / 'LICENSE').read_text(encoding="utf-8"))
        self.assertIn('never edit by hand', (package / 'VENDORED.md').read_text(encoding="utf-8"))
        self.assertFalse((package / 'cyaml.py').exists())
        self.assertFalse((package / '_yaml.py').exists())
        text = (ROOT / 'pyproject.toml').read_text(encoding="utf-8")
        self.assertIn('"lib/pdfmd_yaml/LICENSE"', text)
        self.assertIn('pdfmd_yaml = ["LICENSE", "VENDORED.md"]', text)

    def test_zipapp_always_ships_private_yaml_and_never_copies_installed_yaml(self):
        import zipfile
        with tempfile.TemporaryDirectory(prefix='pdfmd-yaml-pyz-') as folder:
            archive = Path(folder) / 'pdfmd.pyz'
            done = subprocess.run([sys.executable, str(ROOT / 'scripts/build_zipapp.py'), '-o', str(archive)],
                                  env={**os.environ}, stdin=subprocess.DEVNULL, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            with zipfile.ZipFile(archive) as bundle:
                self.assertIn('pdfmd_yaml/__init__.py', bundle.namelist())
                self.assertIn('pdfmd_yaml/LICENSE', bundle.namelist())
                self.assertFalse(any(n.startswith('yaml/') for n in bundle.namelist()))


class Fallback(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='pdfmd-yaml-fallback-')
        self.addCleanup(self.scratch.cleanup)
        self.folder = Path(self.scratch.name)
        shim = self.folder / 'shim'
        shim.mkdir()
        (shim / 'sitecustomize.py').write_text('import sys\nsys.modules["yaml"] = None\n', encoding='utf-8')
        self.env = {**os.environ, 'PYTHONPATH': str(shim), 'PDFMD_CONFIG': '', 'PDFMD_NO_PROMPT': '1',
                    'PDFMD_NO_APP_PATHS': '1', **{key: str(self.folder / key) for key in
                    ('XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'APPDATA', 'LOCALAPPDATA')}}

    def run_pdfmd(self, *args, stdin=None):
        kwargs = {'stdin': subprocess.DEVNULL} if stdin is None else {'input': stdin}
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/pdfmd'), *args], cwd=self.folder,
                              env=self.env, capture_output=True, text=True, **kwargs)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done

    def build_numbered(self):
        import shutil
        if not shutil.which('pandoc'):
            self.skipTest('needs Pandoc')
        done = self.run_pdfmd('doc.md', '--to', 'latex', '--no-backup', '--verbose')
        self.assertIn('pdfmd-line-numbers=true', done.stdout + done.stderr)
        self.assertIn('numbers=left', (self.folder / 'doc.tex').read_text(encoding='utf-8'))

    def test_front_matter_options_work_through_checkout_launcher(self):
        (self.folder / 'doc.md').write_text('---\npdfmd-options: {line-numbers: true}\n---\n\n```python\nx = 1\n```\n')
        self.build_numbered()

    def test_metadata_options_work_through_checkout_launcher(self):
        (self.folder / 'doc.md').write_text('```python\nx = 1\n```\n')
        (self.folder / 'metadata.yaml').write_text('title: Shared YAML\npdfmd-options: {line-numbers: true}\n')
        self.build_numbered()
        self.assertIn('Shared YAML', (self.folder / 'doc.tex').read_text(encoding='utf-8'))

    def test_setup_writes_config_that_subsequent_build_reads(self):
        import pdfmd
        from pdfmd_setup import settings_for
        rows = settings_for(pdfmd.NO_AUTO_KINDS)
        number = next(i for i, row in enumerate(rows, 1) if row.key == 'options.line-numbers')
        self.env['PDFMD_CONFIG'] = str(Path(self.env['XDG_CONFIG_HOME']) / 'pdfmd/config.yaml')
        self.run_pdfmd('--setup', 'plain', stdin=f'{number}\n1\ns\n')
        config = Path(self.env['XDG_CONFIG_HOME']) / 'pdfmd/config.yaml'
        import pdfmd_yaml
        self.assertTrue(pdfmd_yaml.safe_load(config.read_text(encoding="utf-8"))['options']['line-numbers'])
        (self.folder / 'doc.md').write_text('```python\nx = 1\n```\n')
        self.build_numbered()

    def test_version_and_doctor_work_and_doctor_names_fallback(self):
        self.assertIn('pdfmd ', self.run_pdfmd('--version').stdout)
        empty = self.folder / 'empty'
        empty.mkdir()
        self.env['PATH'] = str(empty)
        self.assertIn('YAML: bundled PyYAML 6.0.3 (pure Python)', self.run_pdfmd('--doctor').stdout)

    def test_all_consumers_share_the_same_yaml_and_installed_yaml_wins(self):
        code = '''import sys
sys.path[:0] = [sys.argv[1], sys.argv[1] + '/lib']
import pdfmd
from pdfmd_yaml_support import yaml
assert yaml.__name__ == 'pdfmd_yaml'
assert pdfmd.yaml is yaml
import importlib
lint = importlib.import_module('pdfmd_check.lint')
from pdfmd_history import backups
from pdfmd_restore import yaml as restored_yaml
from pdfmd_office import build
assert lint.yaml is backups.yaml is restored_yaml is build.yaml is yaml
from pdfmd_kits.discovery import _declared_name
from pdfmd_kits.kitfile import _yaml
from pathlib import Path
p = Path('test.kit'); p.write_text('name: fallback\\n')
assert _declared_name(p) == 'fallback'
assert _yaml(p) == {'name': 'fallback'}
'''
        done = subprocess.run([sys.executable, '-c', code, str(ROOT)], cwd=self.folder, env=self.env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        # A synthetic installed module works even on CI where optional PyYAML is absent.
        code = '''import sys, types
sys.path.insert(0, sys.argv[1] + '/lib')
installed = types.ModuleType('yaml'); sys.modules['yaml'] = installed
from pdfmd_yaml_support import yaml
assert yaml is installed
assert 'pdfmd_yaml' not in sys.modules
'''
        done = subprocess.run([sys.executable, '-S', '-c', code, str(ROOT)], env=self.env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
