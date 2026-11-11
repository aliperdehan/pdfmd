"""A watch of another project's namesake must not suppress a build."""
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
            script = root / 'pdfmd.py'
            script.write_text('import time; time.sleep(30)')
            watcher = subprocess.Popen([sys.executable, str(script), '--watch', 'report.md'], cwd=project_a, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
            try:
                for project, expected in [(project_a, 'yes'), (project_b, 'no')]:
                    result = subprocess.run([str(root / 'test'), str(project / 'report.md'), expected], capture_output=True, text=True, timeout=10, env=env)
                    self.assertEqual(result.returncode, 0, f"{project}: {expected}\n" + result.stdout + result.stderr)
            finally:
                watcher.terminate()
                watcher.wait(timeout=10)
