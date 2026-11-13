"""Headless regressions for Colophon's unsaved text protections."""
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


def swift(test, source):
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        (root / 'main.swift').write_text(source)
        env = {**os.environ, 'CLANG_MODULE_CACHE_PATH': str(root / 'clang')}
        built = subprocess.run(['swiftc', '-module-cache-path', str(root / 'modules'), str(root / 'main.swift'), '-o', str(root / 'test')], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=120)
        test.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        done = subprocess.run([str(root / 'test'), str(root)], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=30)
        test.assertEqual(done.returncode, 0, done.stdout + done.stderr)


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'Colophon needs Swift and macOS frameworks')
class LostEdits(unittest.TestCase):
    def test_only_fragment_jumps_bypass_the_dirty_check(self):
        source = (ROOT / 'gui/Sources/Web/WebStudio.swift').read_text()
        method = source[source.index('    func webView(_ webView: WKWebView, decidePolicyFor'):source.index('    /// The file of the project a link', source.index('    func webView(_ webView: WKWebView, decidePolicyFor'))]
        swift(self, r'''
import Foundation
import Darwin
enum Kind { case linkActivated, reload, other, formSubmitted }
enum WKNavigationActionPolicy { case allow, cancel }
class WKWebView { var url: URL? = URL(string: "http://localhost:8000/") }
class Frame { var isMainFrame = true }
class WKNavigationAction {
    var request: URLRequest
    var navigationType: Kind
    var targetFrame: Frame? = Frame()
    init(_ url: String, _ kind: Kind) { request = URLRequest(url: URL(string: url)!); navigationType = kind }
}
class NSWorkspace { static let shared = NSWorkspace(); func open(_ url: URL) {} }
enum NSSound { static func beep() {} }
class Studio {
    var pageURL: URL? = URL(string: "http://localhost:8000/")
    var folder: URL?
    var state: [String: Any] = [:]
    var checks = 0
    var answer = false
    func mayLeavePage() -> Bool { checks += 1; return answer }
    func openInPage(_ name: String) {}
    static func projectFile(for url: URL, folder: URL, current: String?) -> String? { nil }
''' + method + r'''
}
let studio = Studio(), web = WKWebView()
for kind: Kind in [.reload, .other, .linkActivated] {
    let before = studio.checks
    studio.webView(web, decidePolicyFor: WKNavigationAction("http://localhost:8000/", kind)) { if $0 != .cancel { exit(1) } }
    if studio.checks != before + 1 { exit(2) }
}
let before = studio.checks
studio.webView(web, decidePolicyFor: WKNavigationAction("http://localhost:8000/#section", .linkActivated)) { if $0 != .allow { exit(3) } }
if studio.checks != before { exit(4) }
web.url = URL(string: "http://localhost:8000/#section")
studio.webView(web, decidePolicyFor: WKNavigationAction("http://localhost:8000/#section", .other)) { if $0 != .cancel { exit(5) } }
studio.webView(web, decidePolicyFor: WKNavigationAction("http://localhost:8000/#changed", .reload)) { if $0 != .cancel { exit(6) } }
studio.webView(web, decidePolicyFor: WKNavigationAction("http://localhost:8000/#changed", .formSubmitted)) { if $0 != .cancel { exit(7) } }
studio.answer = true
studio.webView(web, decidePolicyFor: WKNavigationAction("http://localhost:8000/#section", .reload)) { if $0 != .allow { exit(8) } }
''')

    def test_unreadable_pop_file_is_not_replaced_but_missing_file_is_recreated(self):
        source = (ROOT / 'gui/Sources/Pop/PopPanel.swift').read_text()
        method = source[source.index('    func savePane(to file: URL)'):source.index('    private func keepPaneOverDisk')]
        swift(self, r'''
import Foundation
import Darwin
class Text { var string = "pane edits" }
class Pane {
    var preambleView = Text()
    var paneOnDisk: Data? = "old".data(using: .utf8)
    var status = ""
    var questions = 0
    func setStatus(_ message: String, error: Bool) { status = message }
    func keepPaneOverDisk(_ file: URL) -> Bool { questions += 1; return false }
''' + method + r'''
}
let file = URL(fileURLWithPath: CommandLine.arguments[1]).appendingPathComponent("preamble.tex")
try! "external".write(to: file, atomically: true, encoding: .utf8)
try! FileManager.default.setAttributes([.posixPermissions: 0], ofItemAtPath: file.path)
if (try? Data(contentsOf: file)) != nil { print("fixture is readable"); exit(9) }
let pane = Pane()
pane.savePane(to: file)
try! FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
if try! String(contentsOf: file, encoding: .utf8) != "external" { exit(1) }
if pane.status.isEmpty || pane.paneOnDisk != "old".data(using: .utf8) { exit(2) }
if pane.preambleView.string != "pane edits" || pane.questions != 0 { exit(3) }
try! FileManager.default.removeItem(at: file)
pane.savePane(to: file)
if try! String(contentsOf: file, encoding: .utf8) != "pane edits" { exit(4) }
try! "changed again".write(to: file, atomically: true, encoding: .utf8)
pane.savePane(to: file)
if pane.questions != 1 || pane.preambleView.string != "changed again" { exit(5) }
''')

    def test_failed_load_disk_answer_keeps_the_document_dirty(self):
        source = (ROOT / 'gui/Sources/Editor/EditorView.swift').read_text()
        method = source[source.index('    func diskChanged()'):source.index('    override class var readableTypes:')]
        swift(self, r'''
import Foundation
import Darwin
enum Change { case changeCleared }
enum Answer { case alertFirstButtonReturn, alertSecondButtonReturn }
enum Settings { static func flag(_ key: String) -> Bool { true } }
class Text {
    var string = "my edits"
    func selectedRange() -> NSRange { NSRange(location: 0, length: 0) }
    func setSelectedRange(_ range: NSRange) {}
}
class Parts { var textView = Text() }
class Controller { var parts = Parts(); var window: Int? = 1 }
class NSAlert {
    static var respond: ((Answer) -> Void)?
    var messageText = "", informativeText = ""
    func addButton(withTitle: String) {}
    func beginSheetModal(for window: Int, completionHandler: @escaping (Answer) -> Void) { Self.respond = completionHandler }
    func runModal() -> Answer { .alertSecondButtonReturn }
}
class EditorDocument {
    static var diskChoice: Bool?
    static var quietErrors = true
    var fileURL: URL?
    var asking = false
    var controller: Controller? = Controller()
    var text = "my edits"
    var isDocumentEdited = true
    var fileModificationDate: Date?
    var fileType: String?
    var lastReloadError: Error?
    func data(ofType: String) throws -> Data { text.data(using: .utf8)! }
    func updateChangeCount(_ change: Change) { isDocumentEdited = false }
    func revert(toContentsOf url: URL, ofType: String) throws { text = try String(contentsOf: url, encoding: .utf8) }
    func tellNotUTF8() {}
    func presentError(_ error: Error) {}
    func presentError(_ error: Error, modalFor: Int, delegate: Any?, didPresent: Any?, contextInfo: Any?) {}
''' + method + r'''
}
let doc = EditorDocument()
let file = URL(fileURLWithPath: CommandLine.arguments[1]).appendingPathComponent("doc.md")
doc.fileURL = file
try! "external".write(to: file, atomically: true, encoding: .utf8)
doc.diskChanged()
try! FileManager.default.removeItem(at: file)
NSAlert.respond?(.alertSecondButtonReturn)
if !doc.isDocumentEdited || doc.text != "my edits" || doc.lastReloadError == nil { exit(1) }
try! "external again".write(to: file, atomically: true, encoding: .utf8)
doc.diskChanged()
NSAlert.respond?(.alertSecondButtonReturn)
if doc.isDocumentEdited || doc.text != "external again" || doc.lastReloadError != nil { exit(2) }
''')
