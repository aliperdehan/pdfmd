"""Restoring Popup defaults removes an app-managed login registration."""
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
class LoginRestore(unittest.TestCase):
    def test_restore_unregisters_only_an_app_managed_item(self):
        source = (ROOT / 'gui/Sources/Settings/Preferences.swift').read_text()
        method = source[source.index('    private func restore(_ tab:'):source.index('\n}\n\n/// A page', source.index('    private func restore(_ tab:'))]
        shim = r'''
import Foundation
import Darwin
struct Item { let tab: String; let key: String }
class Store {
    var values: [String: Int] = [:]
    func object(forKey key: String) -> Any? { values[key] }
}
enum Settings {
    static var store = Store()
    static let items = [Item(tab: "Popup", key: "popLaunchAtLogin")]
    static let texts: [Item] = []
    static var loginEnabled = true
    static func flag(_ key: String) -> Bool { store.values[key, default: 0] != 0 }
    static func set(_ key: String, _ value: Any?) {
        store.values[key] = value as? Int
        if key == "popLaunchAtLogin", let v = value as? Int { loginEnabled = v != 0 }
    }
    static func remove(_ keys: [String]) { for key in keys { store.values.removeValue(forKey: key) } }
}
enum Palette { struct Role { let key: String }; static let roles: [Role] = [] }
class PreferencesController {
    func refresh() {}
    func run() { restore("Popup") }
'''
        main = r'''
}
Settings.store.values["popLaunchAtLogin"] = 1
PreferencesController().run()
if Settings.loginEnabled || Settings.store.object(forKey: "popLaunchAtLogin") != nil { exit(1) }
Settings.loginEnabled = true
PreferencesController().run()
if !Settings.loginEnabled { exit(2) }
Settings.store.values["popLaunchAtLogin"] = 0
PreferencesController().run()
exit(Settings.loginEnabled ? 0 : 3)
'''
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'main.swift').write_text(shim + method + main)
            env = os.environ.copy()
            env['CLANG_MODULE_CACHE_PATH'] = str(root / 'clang')
            subprocess.run(['swiftc', '-module-cache-path', str(root / 'modules'), str(root / 'main.swift'), '-o', str(root / 'test')], check=True, capture_output=True, env=env, timeout=120)
            result = subprocess.run([str(root / 'test')], capture_output=True, text=True, timeout=10, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
