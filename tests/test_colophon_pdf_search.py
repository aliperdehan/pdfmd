"""Late PDF search callbacks cannot change the replacement document's results."""
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
class PDFSearch(unittest.TestCase):
    def test_callbacks_from_old_document_are_ignored(self):
        source = (ROOT / 'gui/Sources/PDF/PDFViewer.swift').read_text()
        callbacks = source[source.index('    func didMatchString('):source.index('    // MARK: toolbar', source.index('    func didMatchString('))]
        shim = r'''
import Foundation
import Darwin
class PDFDocument: NSObject {}
class PDFPage { var document: PDFDocument?; init(_ doc: PDFDocument) { document = doc } }
enum Colour { case systemYellow }
class PDFSelection { var color: Colour?; var pages: [PDFPage]; init(_ doc: PDFDocument) { pages = [PDFPage(doc)] } }
enum Settings { static func string(_ key: String) -> String { "" } }
enum Palette { static func parse(_ text: String) -> Colour? { nil } }
class View { var document: PDFDocument?; var highlightedSelections: [PDFSelection]? }
class Viewer {
    var searching = true
    var matches: [PDFSelection] = []
    var jumpToFirst = false
    var lastHighlight = Date()
    var pdfView = View()
    func select(_ i: Int) {}
    func placeChanged() {}
'''
        main = r'''
}
let old = PDFDocument(), current = PDFDocument(), viewer = Viewer()
viewer.pdfView.document = current
viewer.didMatchString(PDFSelection(old))
viewer.documentDidEndDocumentFind(Notification(name: Notification.Name("end"), object: old))
if !viewer.matches.isEmpty || !viewer.searching { exit(1) }
viewer.didMatchString(PDFSelection(current))
viewer.documentDidEndDocumentFind(Notification(name: Notification.Name("end"), object: current))
exit(viewer.matches.count == 1 && !viewer.searching ? 0 : 2)
'''
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'main.swift').write_text(shim + callbacks + main)
            env = os.environ.copy()
            env['CLANG_MODULE_CACHE_PATH'] = str(root / 'clang')
            subprocess.run(['swiftc', '-module-cache-path', str(root / 'modules'), str(root / 'main.swift'), '-o', str(root / 'test')], check=True, capture_output=True, env=env, timeout=120)
            result = subprocess.run([str(root / 'test')], capture_output=True, text=True, timeout=10, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
