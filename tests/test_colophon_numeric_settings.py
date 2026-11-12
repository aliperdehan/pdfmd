"""Numeric settings are checked before either settings interface stores them."""
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


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'requires the macOS Swift compiler')
class NumericSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        root = Path(cls.folder.name)
        cli = (ROOT / 'gui/Sources/App/CLI.swift').read_text()
        cli = cli[cli.index('enum SettingsCLI {'):cli.index('    static func jsonObject(')] + '\n}\n'
        cli = cli.replace('CFPreferencesCopyAppValue(', 'fakeCopyAppValue(')
        preferences = (ROOT / 'gui/Sources/Settings/Preferences.swift').read_text()
        start = preferences.index('            case .number:', preferences.index('if let item = Settings.items.first(where: { $0.key == id })'))
        branch = preferences[start:preferences.index('            case .choice', start)]
        shim = r'''
import Foundation
import CoreFoundation
import Cocoa
enum PopToolchain { static func find(_ name: String) -> String? { nil }; static func run(_ exe: String, _ args: [String]) -> Int32? { nil } }
class MemoryDefaults: UserDefaults {
    var values: [String: Any] = [:]
    override func object(forKey key: String) -> Any? { values[key] }
    override func set(_ value: Any?, forKey key: String) { values[key] = value }
    override func removeObject(forKey key: String) { values.removeValue(forKey: key) }
}
enum Palette { static func reload() {}; static let roles: [Role] = []
    struct Role { let key: String; let help: String; let category: String }
}
enum Theme { static let categoryNames: [String] = []; static func available() -> [String] { [] }; static func parseHex(_ s: String) -> String? { nil } }
struct PopShortcut { let label: String; static func parse(_ s: String) -> PopShortcut? { nil } }
func monospacedFamilies() -> [String] { [] }
var stored: Any? = NSNumber(value: 1e100)
func fakeCopyAppValue(_ key: CFString, _ domain: CFString) -> Any? { stored }
enum CLI { static let domain = "test" }
class NSTextField { var stringValue: String; init(_ s: String) { stringValue = s } }
class NSAlert { var messageText = ""; var informativeText = ""; func runModal() { alerts.append(informativeText) } }
var alerts: [String] = []
'''
        main = r'''
        default: break
        }
    }
}
let memory = MemoryDefaults()
Settings.store = memory
let mode = CommandLine.arguments[1]
func check(_ ok: Bool, _ reason: String) { if !ok { print(reason); exit(1) } }
if mode == "cli" {
    let entries = SettingsCLI.entries()
    for (key, raw) in [("pdfReloadDebounceMs", "1e100"), ("lineNumberMinDigits", "1e20"), ("fontSize", "0"), ("statusSliceChars", "0"), ("buildStopGrace", "0"), ("popTimeoutS", "-1"), ("pdfReloadDebounceMs", "inf"), ("fontSize", "nan"), ("popWarmWaitS", "1e18"), ("pdfReloadDebounceMs", "1e16")] {
        let result = SettingsCLI.parse(entries.first { $0.key == key }!, raw)
        check(result.value == nil && result.error?.contains("range") == true, "accepted invalid \(key)=\(raw)")
    }
    for item in Settings.items {
        check(SettingsCLI.parse(entries.first { $0.key == item.key }!, entries.first { $0.key == item.key }!.defaultValue).error == nil, "rejected default \(item.key)")
    }
    check(SettingsCLI.parse(entries.first { $0.key == "buildTimeout" }!, "0").error == nil, "zero disables build timeout")
    check(SettingsCLI.parse(entries.first { $0.key == "fontSize" }!, "13.5").error == nil, "fractional point size")
    for key in ["lineNumberMinDigits", "pdfContentsOpenLevels", "pdfSidebarWidth", "popBorderPt"] {
        check(SettingsCLI.parse(entries.first { $0.key == key }!, "0").error == nil, "meaningful zero for \(key)")
    }
    check(SettingsCLI.parse(entries.first { $0.key == "lineNumberMinDigits" }!, String(Double(Int.max).nextDown)).error == nil, "last representable Int")
    check(SettingsCLI.parse(entries.first { $0.key == "lineNumberMinDigits" }!, String(Double(Int.max))).error != nil, "rounded Int.max overflow")
} else if mode == "preferences" {
    memory.values["lineNumberMinDigits"] = 5
    Preferences().enter("lineNumberMinDigits", NSTextField("1e20"))
    check((memory.values["lineNumberMinDigits"] as? Int) == 5, "invalid input was stored")
    check(alerts.first?.contains("range") == true, "valid range was not shown")
    Preferences().enter("lineNumberMinDigits", NSTextField("6"))
    check(Settings.int("lineNumberMinDigits") == 6, "valid input was not stored")
} else if mode == "reading" {
    for value in [1e100, Double.infinity, Double.nan, -1] {
        memory.values["lineNumberMinDigits"] = NSNumber(value: value)
        check(Settings.int("lineNumberMinDigits") == 3, "unsafe stored value did not fall back")
    }
    memory.values["fontSize"] = 0
    check(Settings.number("fontSize") == 13, "invalid font size did not fall back")
} else if mode == "bitmap" {
    let bytes = NSMutableData()
    var rect = CGRect(x: 0, y: 0, width: 10, height: 10)
    let context = CGContext(consumer: CGDataConsumer(data: bytes)!, mediaBox: &rect, nil)!
    context.beginPDFPage(nil); context.fill(rect); context.endPDFPage(); context.closePDF()
    check(PopPDFTools.png(from: bytes as Data, scale: CGFloat(Double(Int.max).nextDown)) == nil, "unrepresentable bitmap dimensions")
    check(PopPDFTools.png(from: bytes as Data, scale: 4) != nil, "ordinary PNG no longer works")
} else if mode == "format" {
    for value in [1e100, Double.infinity, Double.nan] {
        stored = NSNumber(value: value)
        check(SettingsCLI.current("pdfReloadDebounceMs") != nil, "stored number cannot be inspected")
    }
}
'''
        extra = ROOT / 'gui/Sources/Settings/SettingsNumeric.swift'
        sources = [str(ROOT / 'gui/Sources/Settings/Settings.swift'), str(ROOT / 'gui/Sources/Pop/PopPDFTools.swift')]
        if extra.exists():
            sources.append(str(extra))
        # Put the extracted CLI alongside the stubs, without invoking the app or preferences daemon.
        (root / 'main.swift').write_text(shim + cli + '\nclass Preferences {\n func refresh() {}\n func enter(_ id: String, _ sender: Any) { switch Settings.Kind.number {\n' + branch + main)
        cls.env = os.environ.copy()
        cls.env['CLANG_MODULE_CACHE_PATH'] = str(root / 'clang')
        cls.binary = root / 'test'
        result = subprocess.run(['swiftc', '-module-cache-path', str(root / 'modules'), *sources, str(root / 'main.swift'), '-o', str(cls.binary)], capture_output=True, text=True, env=cls.env, timeout=120)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def run_mode(self, mode):
        result = subprocess.run([str(self.binary), mode], capture_output=True, text=True, env=self.env, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cli_rejects_values_outside_consumer_ranges(self):
        self.run_mode('cli')

    def test_preferences_refuses_before_storing_and_names_range(self):
        self.run_mode('preferences')

    def test_invalid_legacy_preferences_use_defaults(self):
        self.run_mode('reading')

    def test_cli_can_inspect_oversized_legacy_numbers(self):
        self.run_mode('format')

    def test_pdf_dimensions_cannot_overflow_bitmap_conversion(self):
        self.run_mode('bitmap')
