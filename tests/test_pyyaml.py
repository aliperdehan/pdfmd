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
        self.assertIn('Permission is hereby granted', (package / 'LICENSE').read_text())
        self.assertIn('never edit by hand', (package / 'VENDORED.md').read_text())
        self.assertFalse((package / 'cyaml.py').exists())
        self.assertFalse((package / '_yaml.py').exists())
        text = (ROOT / 'pyproject.toml').read_text()
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
