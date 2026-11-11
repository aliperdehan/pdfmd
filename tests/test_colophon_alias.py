"""Discovery retains the shell's actual alias value and quoting."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('swiftc'), 'Swift compiler required')
class Alias(unittest.TestCase):
    def test_alias_with_quoted_path_is_discovered_and_runs(self):
        tool = (ROOT / 'gui/Sources/App/PdfmdTool.swift').read_text()
        build = (ROOT / 'gui/Sources/Editor/Build.swift').read_text()
        build = build[build.index('enum PdfmdBuild {'):build.index('/// The build log:')]
        stub = '''enum Settings {
    struct Item { let key: String; let value: Double }
    static let items = [Item(key: "buildStopGrace", value: 0.3)]
    static func number(_ key: String) -> Double { 0.3 }
    static func string(_ key: String) -> String { "" }
}\n'''
        main = '''\nlet candidates = PdfmdTool.candidates(timeout: 5)
if let alias = candidates.first { print(alias.command); print(PdfmdTool.probe(alias.command, timeout: 5) ?? "no version") } else { exit(1) }
'''
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root / 'My Docs' / 'pdfmd.py'
            script.parent.mkdir()
            script.write_text('print("pdfmd 9.8.7")')
            command = shlex.quote(sys.executable) + ' ' + shlex.quote(str(script))
            (root / '.zshrc').write_text('alias pdfmd=' + shlex.quote(command) + '\n')
            (root / 'main.swift').write_text('import Foundation\nimport Darwin\n' + stub + (ROOT / 'gui/Sources/Editor/BuildWatcher.swift').read_text() + build + tool + main)
            env = os.environ.copy()
            env.update(CLANG_MODULE_CACHE_PATH=str(root / 'clang'), HOME=str(root), ZDOTDIR=str(root))
            subprocess.run(['swiftc', '-module-cache-path', str(root / 'modules'), str(root / 'main.swift'), '-o', str(root / 'test')], check=True, capture_output=True, env=env, timeout=120)
            result = subprocess.run([str(root / 'test')], capture_output=True, text=True, timeout=20, env=env, stdin=subprocess.DEVNULL)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), [command, '9.8.7'])
