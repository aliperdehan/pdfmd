"""Check the wait launch arguments without opening an application window."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'Colophon is a Mac app: this check compiles Swift against macOS frameworks')
class OpenWait(unittest.TestCase):
    def test_wait_uses_a_dedicated_instance(self):
        source = (ROOT / 'gui/Sources/App/CLI.swift').read_text()
        function = source[source.index('    static func open(_ files:'):source.index('    // MARK: check')]
        shim = r'''
import Foundation
import Darwin
class Process {
    var executableURL: URL?
    var arguments: [String] = []
    var environment: [String: String]?
    var terminationStatus: Int32 = 0
    func run() throws { print(arguments.joined(separator: "\n")) }
    func waitUntilExit() {}
}
enum CLI {
    static func appURL() -> URL? { URL(fileURLWithPath: "/tmp/Colophon.app") }
    static func fail(_ s: String, code: Int32 = 2) -> Never { exit(code) }
'''
        main = '\n}\nCLI.open([CommandLine.arguments[1]], wait: true)\n'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            document = root / 'a file.md'
            document.write_text('test')
            (root / 'main.swift').write_text(shim + function + main)
            env = os.environ.copy()
            env['CLANG_MODULE_CACHE_PATH'] = str(root / 'clang')
            subprocess.run(['swiftc', '-module-cache-path', str(root / 'modules'), str(root / 'main.swift'), '-o', str(root / 'test')], check=True, capture_output=True, env=env, timeout=120)
            result = subprocess.run([str(root / 'test'), str(document)], capture_output=True, text=True, timeout=10, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            args = result.stdout.splitlines()
            self.assertIn('-n', args)
            self.assertIn('-W', args)
            self.assertEqual(args[-3:], ['--args', '--colophon-wait', str(document)])
