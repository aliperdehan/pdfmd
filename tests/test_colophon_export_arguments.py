"""Export removes complete target arguments while preserving shell escapes."""
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
class ExportArguments(unittest.TestCase):
    def test_escaped_spaces_and_quotes_stay_in_whole_words(self):
        source = (ROOT / 'gui/Sources/Editor/Export.swift').read_text()
        source = source[source.index('enum ExportArguments {'):source.index('// MARK: which engines')]
        main = r'''
let cases = [
    (#"-o my\ output.pdf --verbose"#, "--verbose"),
    (#"--to html --metadata title=\"a\ b\" -o 'out file.pdf'"#, #"--metadata title=\"a\ b\""#),
    (#"--output=old\ file.pdf --verbose"#, "--verbose")
]
for (input, expected) in cases {
    let got = ExportArguments.withoutTarget(input)
    if got != expected { print("expected: \(expected), got: \(got)"); exit(1) }
}
'''
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'main.swift').write_text('import Foundation\n' + source + main)
            env = os.environ.copy()
            env['CLANG_MODULE_CACHE_PATH'] = str(root / 'clang')
            subprocess.run(['swiftc', '-module-cache-path', str(root / 'modules'), str(root / 'main.swift'), '-o', str(root / 'test')], check=True, capture_output=True, env=env, timeout=120)
            result = subprocess.run([str(root / 'test')], capture_output=True, text=True, timeout=10, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
