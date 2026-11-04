import Cocoa

/// A setting changed from another process (`colophon settings set`): the running app reads the preferences again and tells its windows.
enum LiveSettings {
    static let name = Notification.Name("io.github.aliperdehan.pdfmdedit.settingsChanged")

    static func install(domain: String) {
        DistributedNotificationCenter.default().addObserver(forName: name, object: nil, queue: .main) { _ in
            CFPreferencesAppSynchronize(domain as CFString)
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { Settings.remove([]) }   // posts Settings.changed: windows apply what they can
        }
    }

    static func announce() {
        DistributedNotificationCenter.default().postNotificationName(name, object: nil, userInfo: nil, deliverImmediately: true)
    }
}

/// The command line: `colophon VERB ...`, in the manner of `quarto VERB`. It is the app's own program started without any window; the
/// `colophon` script in the app bundle starts it with COLOPHON_CLI=1. Everything the Settings window does can be done here, for scripts
/// and for an agent that is asked to "set my font to Courier".
enum CLI {
    static let verbs: [(name: String, help: String)] = [
        ("render", "colophon render ARGS    build with pdfmd: the same as `pdfmd ARGS`"),
        ("restore", "colophon restore ARGS   `pdfmd --restore ARGS`: the source kept inside a PDF"),
        ("install", "colophon install WHAT   `pdfmd --install WHAT` (fonts, kits, engines)"),
        ("pandoc", "colophon pandoc ARGS    the pandoc that the preview uses"),
        ("check", "colophon check [--json] the versions and places of Colophon, pdfmd, pandoc, the TeX engines and typst"),
        ("eq", "colophon eq SNIPPET OUT.pdf [options]  the equation popup without its window: a LaTeX or Markdown snippet to a cropped vector PDF (--png, --svg too)"),
        ("open", "colophon open [-w] FILE...  open in Colophon (-w waits until its windows close); `colophon FILE` does the same"),
        ("settings", "colophon settings ...  list | get KEY | set KEY VALUE... | reset KEY... | fonts | themes   (--json for programs)"),
        ("help", "colophon help [VERB]"),
        ("version", "colophon version"),
    ]

    /// True when this run is the command line: started by the `colophon` script, or as a program of that name.
    static func isCommandLine(_ args: [String]) -> Bool {
        if ProcessInfo.processInfo.environment["COLOPHON_CLI"] == "1" { return true }
        return (CommandLine.arguments.first as NSString?)?.lastPathComponent == "colophon"
    }

    static var domain: String { ProcessInfo.processInfo.environment["COLOPHON_DOMAIN"] ?? "io.github.aliperdehan.pdfmdedit" }

    static func out(_ s: String) { FileHandle.standardOutput.write(Data((s + "\n").utf8)) }
    static func err(_ s: String) { FileHandle.standardError.write(Data((s + "\n").utf8)) }
    static func fail(_ s: String, code: Int32 = 2) -> Never { err("colophon: " + s); exit(code) }

    static func run(_ args: [String]) -> Never {
        // the settings of the real app, not of the scratch domain a development build would use
        if domain != Bundle.main.bundleIdentifier, let d = UserDefaults(suiteName: domain) { Settings.store = d }
        guard let verb = args.first else { open([], wait: false) }
        let rest = Array(args.dropFirst())
        switch verb {
        case "render": passthrough(tool: .pdfmd, rest)
        case "restore": passthrough(tool: .pdfmd, ["--restore"] + rest)
        case "install": passthrough(tool: .pdfmd, ["--install"] + rest)
        case "pandoc": passthrough(tool: .pandoc, rest)
        case "check": check(json: rest.contains("--json"))
        case "open": open(rest.filter { $0 != "-w" && $0 != "--wait" }, wait: rest.contains("-w") || rest.contains("--wait"))
        case "settings": SettingsCLI.run(rest)
        case "eq": PopCLI.run(rest)
        case "help", "--help", "-h": help(rest.first)
        case "version", "--version", "-V": out("Colophon \(appVersion)"); exit(0)
        default:
            if verb.hasPrefix("-") { fail("unknown option \(verb) (colophon help)") }
            open(args, wait: false)   // `colophon file.md`
        }
    }

    static func help(_ verb: String?) -> Never {
        if let verb, let v = verbs.first(where: { $0.name == verb }) { out(v.help); exit(0) }
        out("Colophon \(appVersion), the pdfmd workbench\n\nusage: colophon VERB [ARGS]   or   colophon FILE...\n")
        for v in verbs { out("  " + v.help) }
        out("\nrender, restore, install and pandoc hand everything after the verb to that program, unchanged, and exit with its status.")
        out("settings changes what the Settings window changes; a running Colophon applies it at once.")
        exit(0)
    }

    // MARK: handing over to pdfmd and pandoc

    enum Tool { case pdfmd, pandoc }

    /// Runs the tool with this terminal's input, output and environment (a login shell would put the PATH in its own order), and exits with its status.
    static func passthrough(tool: Tool, _ args: [String]) -> Never {
        let command: String
        switch tool {
        case .pdfmd:
            let r = PdfmdTool.cachedResolve()
            if let failed = r.failedCommand { fail("the pdfmd command in Settings does not answer: \(failed)", code: 127) }
            guard let best = r.best else { fail("pdfmd was not found (Settings, General, pdfmd command; or `pip install pdfmd-cli`)", code: 127) }
            command = best.command
        case .pandoc:
            guard let path = PdfmdTool.pandoc() else { fail("pandoc was not found (Settings, Studio, pandoc for the preview)", code: 127) }
            command = "'" + path.replacingOccurrences(of: "'", with: "'\\''") + "'"
        }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/zsh")
        p.arguments = ["-c", #"eval "$COLOPHON_TOOL \"\$@\"""#, "colophon"] + args
        var env = ProcessInfo.processInfo.environment
        env["COLOPHON_TOOL"] = command
        env.removeValue(forKey: "COLOPHON_CLI")
        p.environment = env
        do { try p.run() } catch { fail("cannot start the tool: \(error.localizedDescription)", code: 126) }
        signal(SIGINT, SIG_IGN)   // Ctrl-C goes to the tool too; this program waits for its answer
        p.waitUntilExit()
        exit(p.terminationReason == .uncaughtSignal ? 128 + p.terminationStatus : p.terminationStatus)
    }

    // MARK: open

    static func appURL() -> URL? {
        if Bundle.main.bundleURL.pathExtension == "app" { return Bundle.main.bundleURL }
        for dir in ["~/Applications", "/Applications"] {
            let url = URL(fileURLWithPath: ((dir as NSString).expandingTildeInPath as NSString).appendingPathComponent("Colophon.app"))
            if FileManager.default.fileExists(atPath: url.path) { return url }
        }
        return nil
    }

    static func open(_ files: [String], wait: Bool) -> Never {
        guard let app = appURL() else { fail("Colophon.app was not found in ~/Applications or /Applications") }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        p.arguments = (wait ? ["-W"] : []) + ["-a", app.path] + files.map { URL(fileURLWithPath: $0).standardizedFileURL.path }
        do { try p.run() } catch { fail("cannot run open: \(error.localizedDescription)", code: 126) }
        p.waitUntilExit()
        exit(p.terminationStatus)
    }

    // MARK: check

    static func check(json: Bool) -> Never {
        let r = PdfmdTool.cachedResolve()
        let places = PdfmdTool.locate(["pandoc", "lualatex", "xelatex", "pdflatex", "latexmk", "typst", "tectonic"])
        var rows: [(String, String, String)] = [("colophon", appVersion, appURL()?.path ?? "(not installed as an app)")]
        if let best = r.best { rows.append(("pdfmd", best.version, best.shown + (r.explicit ? "  (named in Settings)" : "  (the newest found)"))) }
        else { rows.append(("pdfmd", "-", r.failedCommand.map { "the command in Settings does not answer: \($0)" } ?? "not found")) }
        for o in r.others { rows.append(("pdfmd", o.version, o.shown + "  (also found)")) }
        for name in ["pandoc", "lualatex", "xelatex", "pdflatex", "latexmk", "typst", "tectonic"] {
            if let path = places[name] { rows.append((name, PdfmdTool.versionLine(path).split(separator: " ").first(where: { $0.first?.isNumber == true }).map(String.init) ?? "", path)) }
            else { rows.append((name, "-", "not found")) }
        }
        if json {
            let list = rows.map { ["name": $0.0, "version": $0.1, "where": $0.2] }
            out(String(decoding: (try? JSONSerialization.data(withJSONObject: list, options: [.prettyPrinted, .sortedKeys])) ?? Data(), as: UTF8.self))
        } else {
            for row in rows { out(row.0.padding(toLength: 10, withPad: " ", startingAt: 0) + row.1.padding(toLength: 10, withPad: " ", startingAt: 0) + row.2) }
        }
        exit(0)
    }
}

/// `colophon settings`: the table behind the Settings window, from the shell.
enum SettingsCLI {
    struct Entry {
        let key: String
        let kind: String        // number, flag, choice, text
        let tab: String
        let help: String
        let defaultValue: String
        let choices: [String]?
        var textKind: Settings.TextKind = .free
    }

    static func entries() -> [Entry] {
        func show(_ v: Double) -> String { v == v.rounded() ? String(Int(v)) : String(v) }
        var list: [Entry] = []
        for i in Settings.items {
            switch i.kind {
            case .number: list.append(Entry(key: i.key, kind: "number", tab: i.tab, help: i.help, defaultValue: show(i.value), choices: nil))
            case .flag: list.append(Entry(key: i.key, kind: "flag", tab: i.tab, help: i.help, defaultValue: show(i.value), choices: ["0", "1"]))
            case .choice(let c): list.append(Entry(key: i.key, kind: "choice", tab: i.tab, help: i.help, defaultValue: show(i.value), choices: c.map(show)))
            }
        }
        for t in Settings.texts {
            var names: [String]?
            if case .options(let n) = t.kind { names = n }
            list.append(Entry(key: t.key, kind: "text", tab: t.tab, help: t.help, defaultValue: t.value, choices: names, textKind: t.kind))
        }
        for r in Palette.roles {
            list.append(Entry(key: "color." + r.key, kind: "text", tab: "Colours", help: "colour of \(r.help): #RRGGBB or #LIGHT,#DARK (empty = the theme's)", defaultValue: "", choices: nil))
            list.append(Entry(key: "category." + r.key, kind: "choice", tab: "Colours", help: "the theme category that colours \(r.help) (text = no colouring)", defaultValue: r.category, choices: Theme.categoryNames + ["text"]))
        }
        return list
    }

    static func current(_ key: String) -> String? {
        guard let v = CFPreferencesCopyAppValue(key as CFString, CLI.domain as CFString) else { return nil }
        if let n = v as? NSNumber { let d = n.doubleValue; return d == d.rounded() ? String(Int(d)) : String(d) }
        return v as? String
    }

    /// The stored form of `raw` for this entry, or the reason it is not allowed.
    static func parse(_ e: Entry, _ raw: String) -> (value: Any?, error: String?) {
        let text = raw.trimmingCharacters(in: .whitespaces)
        switch e.kind {
        case "flag":
            switch text.lowercased() {
            case "1", "true", "yes", "on": return (NSNumber(value: 1), nil)
            case "0", "false", "no", "off": return (NSNumber(value: 0), nil)
            default: return (nil, "\(e.key) is a switch: use on or off (1 or 0)")
            }
        case "number":
            guard let d = Double(text) else { return (nil, "\(e.key) is a number, not \"\(raw)\"") }
            return (NSNumber(value: d), nil)
        case "choice":
            if e.key.hasPrefix("category.") {
                guard let c = e.choices, c.contains(text) else { return (nil, "\(e.key) is one of \(e.choices!.joined(separator: ", "))") }
                return (text, nil)
            }
            guard let d = Double(text), let c = e.choices, c.contains(where: { Double($0) == d }) else {
                return (nil, "\(e.key) is one of \(e.choices!.joined(separator: ", ")), not \"\(raw)\"")
            }
            return (NSNumber(value: d), nil)
        default:
            if text.isEmpty { return (nil, nil) }   // empty = back to the default
            switch e.textKind {
            case .themes:
                let names = Theme.available()
                if let hit = names.first(where: { $0.lowercased() == text.lowercased() }) { return (hit, nil) }
                return (nil, "no theme named \"\(raw)\"; found: \(names.joined(separator: ", "))")
            case .fonts:
                let names = monospacedFamilies()
                if let hit = names.first(where: { $0.lowercased() == text.lowercased() }) { return (hit, nil) }
                let near = names.filter { $0.lowercased().contains(text.lowercased()) }
                return (nil, "no monospaced font family \"\(raw)\"" + (near.isEmpty ? " (colophon settings fonts lists them)" : "; did you mean: \(near.prefix(8).joined(separator: ", "))"))
            case .options(let names):
                if let hit = names.first(where: { $0.lowercased() == text.lowercased() }) { return (hit, nil) }
                return (nil, "\(e.key) is one of \(names.joined(separator: ", ")), not \"\(raw)\"")
            case .hotkey:
                if text.lowercased() == "none" { return ("none", nil) }
                guard let s = PopShortcut.parse(text) else {
                    return (nil, "\(e.key) is a shortcut with Control, Option or Command and a key, such as ⌥⇧T or option+shift+t (or none)")
                }
                return (s.label, nil)
            case .free:
                if e.key.hasPrefix("color.") {
                    let parts = text.split(separator: ",").map(String.init)
                    guard !parts.isEmpty, parts.count <= 2, parts.allSatisfy({ Theme.parseHex($0) != nil }) else { return (nil, "\(e.key) is #RRGGBB or #LIGHT,#DARK") }
                }
                return (text, nil)
            }
        }
    }

    static func jsonObject(_ e: Entry) -> [String: Any] {
        var o: [String: Any] = ["key": e.key, "kind": e.kind, "tab": e.tab, "help": e.help, "default": e.defaultValue,
                                "value": current(e.key) ?? e.defaultValue, "changed": current(e.key) != nil]
        if let c = e.choices { o["choices"] = c }
        return o
    }

    static func run(_ args: [String]) -> Never {
        let json = args.contains("--json")
        let rest = args.filter { $0 != "--json" }
        let all = entries()
        func find(_ key: String) -> Entry {
            if let e = all.first(where: { $0.key == key }) { return e }
            let near = all.map(\.key).filter { $0.lowercased().contains(key.lowercased()) }
            CLI.fail("no setting named \"\(key)\"" + (near.isEmpty ? " (colophon settings list)" : "; did you mean: \(near.prefix(8).joined(separator: ", "))"), code: 1)
        }
        guard let sub = rest.first else { CLI.fail("settings: list, get, set, reset, fonts or themes (colophon help settings)") }
        let operands = Array(rest.dropFirst())
        switch sub {
        case "list":
            let shown = operands.isEmpty ? all : all.filter { e in operands.contains { e.tab.lowercased() == $0.lowercased() || e.key.lowercased().contains($0.lowercased()) } }
            if json { CLI.out(String(decoding: (try? JSONSerialization.data(withJSONObject: shown.map(jsonObject), options: [.prettyPrinted, .sortedKeys])) ?? Data(), as: UTF8.self)) }
            else {
                for e in shown {
                    let now = current(e.key)
                    CLI.out(e.key.padding(toLength: 24, withPad: " ", startingAt: 0) + (now ?? e.defaultValue).padding(toLength: 18, withPad: " ", startingAt: 0)
                            + (now == nil ? "" : "(default \(e.defaultValue))  ") + "[\(e.tab)] " + e.help)
                }
            }
            exit(0)
        case "get":
            guard operands.count == 1 else { CLI.fail("settings get KEY") }
            let e = find(operands[0])
            if json { CLI.out(String(decoding: (try? JSONSerialization.data(withJSONObject: jsonObject(e), options: [.sortedKeys])) ?? Data(), as: UTF8.self)) }
            else { CLI.out(current(e.key) ?? e.defaultValue) }
            exit(0)
        case "set":
            guard !operands.isEmpty, operands.count % 2 == 0 else { CLI.fail("settings set KEY VALUE [KEY VALUE ...]") }
            var writes: [(String, Any?)] = []
            for i in stride(from: 0, to: operands.count, by: 2) {
                let e = find(operands[i])
                let (value, error) = parse(e, operands[i + 1])
                if let error { CLI.fail(error, code: 1) }
                writes.append((e.key, value))
            }
            for (key, value) in writes { CFPreferencesSetAppValue(key as CFString, value as CFPropertyList?, CLI.domain as CFString) }
            CFPreferencesAppSynchronize(CLI.domain as CFString)
            LiveSettings.announce()
            for (key, _) in writes { CLI.out("\(key) = \(current(key) ?? "(default)")") }
            exit(0)
        case "reset":
            guard !operands.isEmpty else { CLI.fail("settings reset KEY... (or --all)") }
            let keys = operands == ["--all"] ? all.map(\.key).filter { current($0) != nil } : operands.map { find($0).key }
            for key in keys { CFPreferencesSetAppValue(key as CFString, nil, CLI.domain as CFString) }
            CFPreferencesAppSynchronize(CLI.domain as CFString)
            LiveSettings.announce()
            CLI.out(keys.isEmpty ? "nothing was changed" : "back to the default: " + keys.joined(separator: ", "))
            exit(0)
        case "fonts": CLI.out(monospacedFamilies().joined(separator: "\n")); exit(0)
        case "themes": CLI.out(Theme.available().joined(separator: "\n")); exit(0)
        default: CLI.fail("settings \(sub)? list, get, set, reset, fonts or themes")
        }
    }
}
