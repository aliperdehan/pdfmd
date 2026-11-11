"""Exercise the document watcher without starting Colophon."""
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


@unittest.skipUnless(shutil.which('swiftc'), 'Swift compiler required')
class DiskWatcher(unittest.TestCase):
    def test_recreated_file_and_later_write_are_watched(self):
        source = (ROOT / 'gui/Sources/Editor/DiskWatcher.swift').read_text().replace('import Cocoa', 'import Foundation\nimport Darwin')
        main = r'''
enum Settings { static func number(_ key: String) -> Double { 50 } }
let url = URL(fileURLWithPath: CommandLine.arguments[1])
try! "initial".write(to: url, atomically: false, encoding: .utf8)
var seen = [String]()
let watcher = DiskWatcher(url: url) { seen.append((try? String(contentsOf: url, encoding: .utf8)) ?? "missing") }
DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { try! FileManager.default.removeItem(at: url) }
DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { try! "returned".write(to: url, atomically: false, encoding: .utf8) }
DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { try! "changed".write(to: url, atomically: false, encoding: .utf8) }
DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
    watcher.stop()
    print(seen)
    exit(seen.contains("returned") && seen.contains("changed") ? 0 : 1)
}
dispatchMain()
'''
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'main.swift').write_text(source + main)
            env = os.environ.copy()
            env['CLANG_MODULE_CACHE_PATH'] = str(root / 'clang')
            subprocess.run(['swiftc', '-module-cache-path', str(root / 'modules'), str(root / 'main.swift'), '-o', str(root / 'test')], check=True, capture_output=True, env=env, timeout=120)
            result = subprocess.run([str(root / 'test'), str(root / 'source.md')], capture_output=True, text=True, timeout=10, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
