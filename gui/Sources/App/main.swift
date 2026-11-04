import Cocoa

let args = Array(CommandLine.arguments.dropFirst())

if args.contains("--version") { print("Colophon \(appVersion)"); exit(0) }
// `--set key=value` overrides a setting for this run (benchmark and smoke test).
for (i, a) in args.enumerated() where a == "--set" && i + 1 < args.count {
    let kv = args[i + 1].split(separator: "=", maxSplits: 1).map(String.init)
    // the argument domain: lasts for this run only (UserDefaults.set wrote into the app's real settings for good)
    if kv.count == 2 {
        var domain = UserDefaults.standard.volatileDomain(forName: UserDefaults.argumentDomain)
        domain[kv[0]] = Double(kv[1]) ?? kv[1]
        UserDefaults.standard.setVolatileDomain(domain, forName: UserDefaults.argumentDomain)
    }
}

if args.contains("--fonts") { print(monospacedFamilies().joined(separator: "\n")); exit(0) }
if args.contains("--themes") { print(Theme.available().joined(separator: "\n")); exit(0) }
if args.contains("--settings") { print(Settings.listing()); print("font in use: \(editorFont().fontName) \(editorFont().pointSize) pt"); print(); print(Palette.listing()); exit(0) }

// `--gen MB PATH` writes the benchmark's generated document, to open it by hand.
if let i = args.firstIndex(of: "--gen"), i + 2 < args.count {
    try! Bench.generate(mb: Double(args[i + 1]) ?? 10).write(toFile: args[i + 2], atomically: true, encoding: .utf8)
    exit(0)
}

let app = NSApplication.shared
_ = DocController()

if args.contains("--bench") { Bench.run(args); exit(0) }
if let i = args.firstIndex(of: "--smoke"), i + 1 < args.count { Smoke.run(args[i + 1]); exit(0) }
if let i = args.firstIndex(of: "--smoke-prefs"), i + 1 < args.count { PrefsSmoke.run(args[i + 1]); exit(0) }
if let i = args.firstIndex(of: "--smoke-pdf"), i + 1 < args.count { PDFSmoke.run(args[i + 1]); exit(0) }
if let i = args.firstIndex(of: "--smoke-build"), i + 1 < args.count { BuildSmoke.run(args[i + 1], real: args.contains("--real")); exit(0) }
if let i = args.firstIndex(of: "--bench-pdf"), i + 1 < args.count { PDFSmoke.bench(args[i + 1]); exit(0) }
if args.contains("--live-pdf") { PDFLive.run(args) }
if let i = args.firstIndex(of: "--smoke-save"), i + 1 < args.count { Smoke.save(args[i + 1]); exit(0) }

let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
