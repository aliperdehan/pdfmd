"""Tool discovery must not leave an unresponsive child behind."""
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


@unittest.skipUnless(shutil.which('swiftc'), 'Swift compiler required')
class ToolTimeout(unittest.TestCase):
    def test_timeout_kills_a_child_ignoring_term(self):
        source = (ROOT / 'gui/Sources/App/PdfmdTool.swift').read_text()
        function = source[source.index('    static func run(_ script:'):source.rindex('\n}')]
        build = (ROOT / 'gui/Sources/Editor/Build.swift').read_text()
        build = build[build.index('enum PdfmdBuild {'):build.index('/// The build log:')]
        stub = 'enum Settings { struct Item { let key: String; let value: Double }; static let items = [Item(key: "buildStopGrace", value: 0.3)]; static func number(_ key: String) -> Double { 0.3 } }\n'
        main = r'''
let script = #"/bin/sh -c 'trap "" TERM; echo $$ > "$PDFMD_CMD"; while :; do /bin/sleep 1; done'"#
_ = Tool.run(script, command: CommandLine.arguments[1], interactive: false, timeout: 0.3)
Thread.sleep(forTimeInterval: 0.7)
let contents = (try? String(contentsOfFile: CommandLine.arguments[1], encoding: .utf8)) ?? ""
let pid = pid_t(contents.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 0
if pid <= 0 { exit(2) }
exit(kill(pid, 0) == -1 && errno == ESRCH ? 0 : 1)
'''
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'main.swift').write_text('import Foundation\nimport Darwin\n' + stub + (ROOT / 'gui/Sources/Editor/BuildWatcher.swift').read_text() + build + 'enum Tool {\n' + function + '\n}\n' + main)
            env = os.environ.copy()
            env.update(CLANG_MODULE_CACHE_PATH=str(root / 'clang'), HOME=str(root), ZDOTDIR=str(root))
            subprocess.run(['swiftc', '-module-cache-path', str(root / 'modules'), str(root / 'main.swift'), '-o', str(root / 'test')], check=True, capture_output=True, env=env, timeout=120)
            with (root / 'output').open('w+') as output:
                process = subprocess.Popen([str(root / 'test'), str(root / 'pid')], stdout=output, stderr=output, env=env, start_new_session=True)
                try:
                    status = process.wait(timeout=12)
                    output.seek(0)
                    self.assertEqual(status, 0, output.read())
                finally:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
