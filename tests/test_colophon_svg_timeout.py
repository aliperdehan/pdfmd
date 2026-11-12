"""SVG export must leave the main queue free and stop a stalled converter."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'requires the macOS Swift compiler')
class SVGTimeout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        root = Path(cls.folder.name)
        source = (ROOT / 'gui/Sources/Pop/PopToolchain.swift').read_text()
        runner = source[source.index('    /// Runs a helper'):source.rindex('\n}')]
        build = (ROOT / 'gui/Sources/Editor/Build.swift').read_text()
        build = build[build.index('enum PdfmdBuild {'):build.index('/// The build log:')]
        pdf = (ROOT / 'gui/Sources/Pop/PopPDFTools.swift').read_text()
        async_call = 'PopPDFTools.svg(from: Data(), completion: finish)'
        if 'completion:' not in pdf:
            # The pre-fix saveAs path calls this directly on the main thread.
            async_call = 'finish(.success(PopPDFTools.svg(from: Data())))'
        shim = r'''
import Foundation
import Darwin
let converter = CommandLine.arguments[1]
enum Settings {
    struct Item { let key: String; let value: Double }
    static let items = [Item(key: "buildStopGrace", value: 0.2)]
    static func number(_ key: String) -> Double { key == "buildStopGrace" ? 0.2 : 1 }
    static func formatNumber(_ value: Double) -> String { String(value) }
}
enum PopToolchain {
    static var environment: [String: String] { ProcessInfo.processInfo.environment }
    static func find(_ name: String) -> String? { name == URL(fileURLWithPath: converter).lastPathComponent ? converter : nil }
'''
        main = r'''
}
var returned = false
var beats = 0
let start = Date()
let ticker = DispatchSource.makeTimerSource(queue: .main)
ticker.schedule(deadline: .now(), repeating: .milliseconds(10))
ticker.setEventHandler { beats += 1 }
ticker.resume()
func finish(_ result: Result<Data?, Error>) {
    dispatchPrecondition(condition: .onQueue(.main))
    guard returned else { print("blocked main queue"); exit(1) }
    let mode = CommandLine.arguments[2]
    switch result {
    case .success(let data):
        guard mode == "success", data == Data("<svg/>".utf8) else { print("unexpected success"); exit(2) }
    case .failure(let error):
        let message = error.localizedDescription
        guard mode == "timeout", message.contains(URL(fileURLWithPath: converter).lastPathComponent), message.contains("after 1.0 s"), beats >= 5, Date().timeIntervalSince(start) < 5 else { print("\(message) beats=\(beats) elapsed=\(Date().timeIntervalSince(start)) mode=\(mode)"); exit(3) }
        let pidFile = ProcessInfo.processInfo.environment["CONVERTER_PID"]!
        let pid = pid_t((try? String(contentsOfFile: pidFile, encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "") ?? 0
        guard pid > 0, kill(pid, 0) == -1, errno == ESRCH else { print("converter still alive"); exit(4) }
    }
    let files = (try? FileManager.default.contentsOfDirectory(atPath: FileManager.default.temporaryDirectory.path)) ?? []
    guard !files.contains(where: { $0.hasPrefix("pop-svg-") }) else { print("temporary PDF not cleaned up"); exit(5) }
    print("finished on main queue"); exit(0)
}
DispatchQueue.main.async {
CALL
    returned = true
}
dispatchMain()
'''.replace('CALL', async_call)
        (root / 'main.swift').write_text(shim + runner + main)
        (root / 'BuildRunner.swift').write_text('import Foundation\nimport Darwin\n' + build)
        cls.env = os.environ.copy()
        cls.env['CLANG_MODULE_CACHE_PATH'] = str(root / 'clang')
        cls.binary = root / 'test'
        compile_result = subprocess.run(['swiftc', '-module-cache-path', str(root / 'modules'), str(root / 'main.swift'), str(root / 'BuildRunner.swift'), str(ROOT / 'gui/Sources/Editor/BuildWatcher.swift'), str(ROOT / 'gui/Sources/Pop/PopPDFTools.swift'), '-o', str(cls.binary)], capture_output=True, text=True, env=cls.env, timeout=120)
        if compile_result.returncode:
            raise AssertionError(compile_result.stdout + compile_result.stderr)

    def run_converter(self, name, mode):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tool = root / name
            tool.write_text('#!/bin/sh\n' + ('trap "" TERM\necho $$ > "$CONVERTER_PID"\nwhile :; do /bin/sleep 1; done\n' if mode == 'timeout' else 'for out do :; done\nprintf "<svg/>" > "$out"\n'))
            tool.chmod(0o755)
            env = dict(self.env, TMPDIR=str(root), CONVERTER_PID=str(root / 'pid'))
            with (root / 'output').open('w+') as output:
                process = subprocess.Popen([str(self.binary), str(tool), mode], stdin=subprocess.DEVNULL, stdout=output, stderr=output, env=env, start_new_session=True)
                try:
                    try:
                        status = process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        self.fail('SVG converter blocked the main queue or exceeded the existing timeout and grace')
                    output.seek(0)
                    self.assertEqual(status, 0, output.read())
                finally:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_pdftocairo_timeout_kills_converter_and_keeps_main_queue_free(self):
        self.run_converter('pdftocairo', 'timeout')

    def test_mutool_timeout_names_converter_and_limit(self):
        self.run_converter('mutool', 'timeout')

    def test_successful_conversion_and_temporary_file_cleanup(self):
        self.run_converter('pdftocairo', 'success')

    def test_save_panel_uses_asynchronous_svg_completion(self):
        panel = (ROOT / 'gui/Sources/Pop/PopPanel.swift').read_text()
        branch = panel[panel.index('        case "svg":', panel.index('    @objc func saveAs')):]
        branch = branch[:branch.index('        default:')]
        self.assertIn('PopPDFTools.svg(from: pdf) {', branch)
        self.assertIn('error.localizedDescription', branch)
        self.assertIn('return', branch)
