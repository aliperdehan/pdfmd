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
