"""Exercise Colophon's build runner without starting the application."""
import os
import signal
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
class BuildStop(unittest.TestCase):
    def test_timeout_finishes_when_child_ignores_term_and_holds_pipe(self):
        source = (ROOT / 'gui/Sources/Editor/Build.swift').read_text()
        runner = source[source.index('enum PdfmdBuild {'):source.index('/// The build log:')]
        main = r'''
let file = URL(fileURLWithPath: CommandLine.arguments[1])
PdfmdBuild.run(command: "/bin/sh -c 'trap \"\" TERM; while :; do /bin/sleep 1; done'", arguments: "", file: file, timeout: 0.3, output: { _ in }, done: { result in
    print(result.timedOut ? "timed out" : "wrong result")
    exit(result.timedOut ? 0 : 1)
})
DispatchQueue.main.asyncAfter(deadline: .now() + 8) { exit(2) }
dispatchMain()
'''
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'main.swift').write_text('import Foundation\nimport Darwin\nenum Settings { struct Item { let key: String; let value: Double }; static let items = [Item(key: "buildStopGrace", value: 0.3)]; static func number(_ key: String) -> Double { 0.3 } }\n' + (ROOT / 'gui/Sources/Editor/BuildWatcher.swift').read_text() + runner + main)
            env = os.environ.copy()
            env['CLANG_MODULE_CACHE_PATH'] = str(root / 'clang')
            subprocess.run(['swiftc', '-module-cache-path', str(root / 'modules'), str(root / 'main.swift'), '-o', str(root / 'test')], check=True, capture_output=True, env=env, timeout=120)
            with (root / 'output').open('w+') as output:
                process = subprocess.Popen([str(root / 'test'), str(root / 'source.md')], stdout=output, stderr=output, env=env, start_new_session=True)
                try:
                    status = process.wait(timeout=12)
                    output.seek(0)
                    text = output.read()
                    self.assertEqual(status, 0, text)
                    self.assertIn('timed out', text)
                finally:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
