"""A watch of another project's namesake must not suppress a build."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'Colophon is a Mac app: this check compiles Swift against macOS frameworks')
class WatcherMatch(unittest.TestCase):
    def test_different_canonical_source_is_not_the_watcher(self):
        source = (ROOT / 'gui/Sources/Editor/Build.swift').read_text()
        runner = source[source.index('enum PdfmdBuild {'):source.index('/// The build log:')]
        main = r'''
if CommandLine.arguments.count > 1 {
    let target = URL(fileURLWithPath: CommandLine.arguments[1])
    let found = BuildWatcher.find(target) != nil
    exit(found == (CommandLine.arguments[2] == "yes") ? 0 : 1)
}
let file = URL(fileURLWithPath: "/project-B/report.md")
let other = "python3 pdfmd.py --watch /project-A/report.md"
exit(PdfmdBuild.watcher(for: file, listing: other) == nil ? 0 : 1)
'''
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stub = 'enum Settings { struct Item { let key: String; let value: Double }; static let items = [Item(key: "buildStopGrace", value: 3)]; static func number(_ key: String) -> Double { 3 } }\n'
            (root / 'main.swift').write_text('import Foundation\nimport Darwin\n' + stub + (ROOT / 'gui/Sources/Editor/BuildWatcher.swift').read_text() + runner + main)
            env = os.environ.copy()
            env['CLANG_MODULE_CACHE_PATH'] = str(root / 'clang')
            subprocess.run(['swiftc', '-module-cache-path', str(root / 'modules'), str(root / 'main.swift'), '-o', str(root / 'test')], check=True, capture_output=True, env=env, timeout=120)
            result = subprocess.run([str(root / 'test')], capture_output=True, text=True, timeout=10, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            project_a = root / 'project A'
            project_b = root / 'project B'
            project_a.mkdir()
            project_b.mkdir()
            (project_a / "report.md").write_text("A")
            (project_b / "report.md").write_text("B")
            # Wait for the real watcher, not a sleeping stand-in: process discovery
            # can run before Python has even received its --watch arguments under load.
            log_path = root / 'watch.log'
            with log_path.open('w') as log:
                watcher = subprocess.Popen([sys.executable, '-u', str(ROOT / 'scripts/pdfmd'), '--watch', 'report.md',
                                            '--to', 'html', '--no-auto', 'font', '--no-backup'],
                                           cwd=project_a, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                           env=env, start_new_session=True)
                try:
                    deadline = time.monotonic() + 120
                    while True:
                        # A separate reader cannot move the child's write offset.
                        text = log_path.read_text()
                        if any(line.startswith('WATCH  ') and ': watching ' in line for line in text.splitlines()):
                            break
                        self.assertIsNone(watcher.poll(), text)
                        self.assertLess(time.monotonic(), deadline, 'watcher never became ready:\n' + text)
                        time.sleep(0.05)
                    for project, expected in [(project_a, 'yes'), (project_b, 'no')]:
                        deadline = time.monotonic() + 120
                        while True:
                            result = subprocess.run([str(root / 'test'), str(project / 'report.md'), expected],
                                                    capture_output=True, text=True, timeout=30, env=env)
                            if result.returncode == 0 or expected == 'no' or time.monotonic() >= deadline:
                                break
                            self.assertIsNone(watcher.poll(), text)
                            time.sleep(0.05)
                        self.assertEqual(result.returncode, 0, f"{project}: {expected}\n" + result.stdout + result.stderr)
                finally:
                    # Stop any initial build too, even if the probe failed before it finished.
                    os.killpg(watcher.pid, signal.SIGTERM)
                    watcher.wait(timeout=30)
