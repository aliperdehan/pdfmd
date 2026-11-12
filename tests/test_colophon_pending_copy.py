"""A pending copy belongs to the request made when copy was pressed."""
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
class PendingCopy(unittest.TestCase):
    def test_old_completion_does_not_copy_after_an_edit(self):
        source = (ROOT / 'gui/Sources/Pop/PopPanel.swift').read_text()
        field = next(line for line in source.splitlines() if 'var wantCopy' in line)
        copy = source[source.index('    @objc func copyRendered()'):source.index('    func finishCopy(', source.index('    @objc func copyRendered()'))]
        start = source.index('                if self.wantCopy')
        success = source[start:source.index('            case .failure', start)]
        shim = r'''
import Foundation
import Darwin
class Input { var string = "" }
class PopController: NSObject {
    var input = Input()
    var lastPDF: Data?
    var lastKey: String?
    var copies = 0
    func makeRequest(_ text: String) -> String { text }
    static func key(_ text: String) -> String { text }
    func schedule(after: TimeInterval) {}
    func finishCopy(_ pdf: Data) { copies += 1 }
'''
        main = r'''
}
let pop = PopController()
pop.input.string = "A"
pop.copyRendered()
pop.input.string = "B"
pop.success(key: "A")
if pop.copies != 0 { exit(1) }
pop.copyRendered()
pop.success(key: "A")
if pop.copies != 0 { exit(2) }
pop.success(key: "B")
exit(pop.copies == 1 ? 0 : 3)
'''
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'main.swift').write_text(shim + field + '\n' + copy + '\nfunc success(key: String) { let pdf = Data()\n' + success + '\n}\n' + main)
            env = os.environ.copy()
            env['CLANG_MODULE_CACHE_PATH'] = str(root / 'clang')
            subprocess.run(['swiftc', '-module-cache-path', str(root / 'modules'), str(root / 'main.swift'), '-o', str(root / 'test')], check=True, capture_output=True, env=env, timeout=120)
            result = subprocess.run([str(root / 'test')], capture_output=True, text=True, timeout=10, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
