import Cocoa

/// `pdfmdedit --smoke-cli`: the command line, as a program started the way the `colophon` script starts it, on a scratch settings domain.
/// Checks settings list/get/set/reset (values, validation, the names it suggests, a set that is all or nothing, fonts and themes spelled in
/// any case), that a running app applies a change at once, and that render, restore, install and pandoc hand their arguments over unchanged
/// and exit with the tool's status.
enum CLISmoke {
    static let domain = "io.github.aliperdehan.pdfmdedit.smokecli"

    struct Answer { let status: Int32; let out: String; let err: String }

    static func colophon(_ args: [String], extra: [String: String] = [:]) -> Answer {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath()
        p.arguments = args
        var env = ProcessInfo.processInfo.environment
        env["COLOPHON_CLI"] = "1"
        env["COLOPHON_DOMAIN"] = domain
        for (k, v) in extra { env[k] = v }
        p.environment = env
        let o = Pipe(), e = Pipe()
        p.standardOutput = o
        p.standardError = e
        try! p.run()
        var od = Data(), ed = Data()
        let g = DispatchGroup()
        g.enter(); DispatchQueue.global().async { od = o.fileHandleForReading.readDataToEndOfFile(); g.leave() }
        g.enter(); DispatchQueue.global().async { ed = e.fileHandleForReading.readDataToEndOfFile(); g.leave() }
        p.waitUntilExit(); g.wait()
        return Answer(status: p.terminationStatus, out: String(decoding: od, as: UTF8.self).trimmingCharacters(in: .newlines), err: String(decoding: ed, as: UTF8.self).trimmingCharacters(in: .newlines))
    }

    static func run() {
        NSApplication.shared.setActivationPolicy(.prohibited)
        UserDefaults.standard.removePersistentDomain(forName: domain)
        CFPreferencesAppSynchronize(domain as CFString)
        Settings.store = UserDefaults(suiteName: domain)!
        defer { UserDefaults.standard.removePersistentDomain(forName: domain) }
        var failures = 0
        func check(_ name: String, _ ok: Bool, _ detail: String = "") {
            print("\(ok ? "ok  " : "FAIL") \(name) \(detail)")
            if !ok { failures += 1 }
        }
        let fm = FileManager.default
        let dir = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("pdfmdedit-smoke-cli-\(getpid())")
        try! fm.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: dir) }

        // help and version
        let help = colophon(["help"])
        check("help lists the verbs", help.status == 0 && ["render", "restore", "settings", "check", "open"].allSatisfy { help.out.contains("colophon \($0)") }, help.out.prefix(60).description)
        check("version", colophon(["version"]).out == "Colophon \(appVersion)")
        check("an unknown option is an error", colophon(["--bogus"]).status == 2)

        // settings
        check("get a default", colophon(["settings", "get", "fontSize"]).out == "13")
        let set1 = colophon(["settings", "set", "fontSize", "15"])
        check("set a number", set1.status == 0 && colophon(["settings", "get", "fontSize"]).out == "15", set1.err)
        check("the app's own reading sees it", Settings.number("fontSize") == 15, "\(Settings.number("fontSize"))")
        let list = colophon(["settings", "list", "--json"])
        let parsed = (try? JSONSerialization.jsonObject(with: Data(list.out.utf8))) as? [[String: Any]]
        check("list --json is a list of every setting", (parsed?.count ?? 0) > 60, "\(parsed?.count ?? 0)")
        let fs = parsed?.first { $0["key"] as? String == "fontSize" }
        check("it says what is changed and the default", fs?["value"] as? String == "15" && fs?["default"] as? String == "13" && fs?["changed"] as? Bool == true, "\(fs ?? [:])")
        check("list of one tab", colophon(["settings", "list", "Build"]).out.contains("buildTimeout") && !colophon(["settings", "list", "Build"]).out.contains("fontSize"))
        check("reset", colophon(["settings", "reset", "fontSize"]).status == 0 && colophon(["settings", "get", "fontSize"]).out == "13")

        check("a switch takes on/off", colophon(["settings", "set", "statusLines", "off"]).status == 0 && colophon(["settings", "get", "statusLines"]).out == "0")
        let bad = colophon(["settings", "set", "statusLines", "maybe"])
        check("a wrong value is refused, said and exit 1", bad.status == 1 && bad.err.contains("on or off"), bad.err)
        let near = colophon(["settings", "get", "fontsize"])
        check("a wrong name suggests the right one", near.status == 1 && near.err.contains("fontSize"), near.err)
        let atomic = colophon(["settings", "set", "fontSize", "20", "statusLines", "nope"])
        check("a set with one wrong value changes nothing", atomic.status == 1 && colophon(["settings", "get", "fontSize"]).out == "13")
        check("a choice is checked", colophon(["settings", "set", "pdfDisplayMode", "9"]).status == 1 && colophon(["settings", "set", "pdfDisplayMode", "3"]).status == 0)

        let fonts = colophon(["settings", "fonts"]).out.split(separator: "\n").map(String.init)
        if let menlo = fonts.first(where: { $0 == "Menlo" }) {
            let r = colophon(["settings", "set", "fontName", menlo.lowercased()])
            check("a font in any case is stored as its family", r.status == 0 && colophon(["settings", "get", "fontName"]).out == "Menlo", r.err)
        } else { print("skip  Menlo is not installed") }
        let nofont = colophon(["settings", "set", "fontName", "Papyrus Mono Nonexistent"])
        check("an unknown font is refused", nofont.status == 1 && nofont.err.contains("no monospaced font"), nofont.err)
        let dark = colophon(["settings", "set", "themeDark", "anura (dark)"])
        check("a theme in any case is stored as its name", dark.status == 0 && colophon(["settings", "get", "themeDark"]).out == "Anura (Dark)", dark.err)
        check("a colour is checked", colophon(["settings", "set", "color.heading", "red"]).status == 1 && colophon(["settings", "set", "color.heading", "#112233,#445566"]).status == 0)
        check("reset --all", colophon(["settings", "reset", "--all"]).status == 0 && colophon(["settings", "get", "statusLines"]).out == "1" && colophon(["settings", "get", "pdfDisplayMode"]).out == "1")

        // a running app applies it
        LiveSettings.install(domain: domain)
        var changed = false
        let token = NotificationCenter.default.addObserver(forName: Settings.changed, object: nil, queue: .main) { _ in changed = true }
        _ = colophon(["settings", "set", "statusBar", "0"])
        check("a running app is told", PDFSmoke.wait(10) { changed && !Settings.flag("statusBar") }, "changed \(changed), statusBar \(Settings.flag("statusBar"))")
        NotificationCenter.default.removeObserver(token)
        _ = colophon(["settings", "reset", "--all"])

        // hand-over to pdfmd and pandoc: a stand-in that prints its arguments
        let fake = dir.appendingPathComponent("fake pdfmd.sh")
        try! """
        #!/bin/sh
        if [ "$1" = "--version" ]; then echo "pdfmd 9.9.9"; exit 0; fi
        printf '%s|' "$@"; echo
        exit 7
        """.write(to: fake, atomically: true, encoding: .utf8)
        try! fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: fake.path)
        let quoted = "'" + fake.path + "'"
        check("pdfmdCommand names a stand-in", colophon(["settings", "set", "pdfmdCommand", quoted]).status == 0)
        let r1 = colophon(["render", "a.md", "b c", "--x=1", "it's"])
        check("render hands everything over unchanged", r1.out == "a.md|b c|--x=1|it's|", r1.out + " / " + r1.err)
        check("and exits with the tool's status", r1.status == 7, "\(r1.status)")
        check("restore is pdfmd --restore", colophon(["restore", "doc.pdf"]).out == "--restore|doc.pdf|")
        check("install is pdfmd --install", colophon(["install", "fonts"]).out == "--install|fonts|")
        let pandoc = colophon(["pandoc", "--version"])
        check("pandoc hands over to pandoc", pandoc.status == 0 && pandoc.out.hasPrefix("pandoc"), pandoc.out.prefix(40).description)
        let chk = colophon(["check", "--json"])
        let rows = (try? JSONSerialization.jsonObject(with: Data(chk.out.utf8))) as? [[String: String]]
        check("check --json lists colophon, pdfmd and pandoc", rows?.contains { $0["name"] == "colophon" } == true && rows?.first { $0["name"] == "pdfmd" }?["version"] == "9.9.9" && rows?.contains { $0["name"] == "pandoc" } == true, chk.out.prefix(80).description)
        _ = colophon(["settings", "reset", "pdfmdCommand"])

        print(failures == 0 ? "CLI SMOKE OK" : "CLI SMOKE FAILED (\(failures))")
        exit(failures == 0 ? 0 : 1)
    }
}
