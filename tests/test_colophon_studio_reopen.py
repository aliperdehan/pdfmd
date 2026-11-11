"""A newly created preview pane needs content even after an earlier render."""
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
class StudioReopen(unittest.TestCase):
    def test_fresh_pane_renders_after_an_earlier_preview(self):
        source = (ROOT / 'gui/Sources/Studio/Studio.swift').read_text()
        method = source[source.index('    private func applyMode()'):source.index('\n}', source.index('    private func applyMode()'))]
        shim = r'''
import Foundation
import Darwin
class HTML { var url: URL? }
class Pane {
    var html = HTML()
    func showMode(_ pdf: Bool, hasPDF: Bool) {}
}
class StudioController {
    var pane: Pane? = Pane()
    var showsPDF = false
    var pdfURL: URL?
    var renders = 1
    var editedSinceRender = false
    var calls = 0
    func loadPDF() {}
    func render() { calls += 1; pane?.html.url = URL(fileURLWithPath: "/tmp/preview.html") }
    func apply() { applyMode() }
'''
        main = r'''
}
let studio = StudioController()
studio.apply()
if studio.calls != 1 { exit(1) }
studio.apply()
exit(studio.calls == 1 ? 0 : 2)
'''
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'main.swift').write_text(shim + method + main)
            env = os.environ.copy()
            env['CLANG_MODULE_CACHE_PATH'] = str(root / 'clang')
            subprocess.run(['swiftc', '-module-cache-path', str(root / 'modules'), str(root / 'main.swift'), '-o', str(root / 'test')], check=True, capture_output=True, env=env, timeout=120)
            result = subprocess.run([str(root / 'test')], capture_output=True, text=True, timeout=10, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
