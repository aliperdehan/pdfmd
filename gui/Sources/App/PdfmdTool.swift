import Foundation

/// The pdfmd the app works with. Several can exist side by side (a release installed by Homebrew or pipx, a checkout that the
/// terminal reaches through an alias), and they differ in version; the app takes the newest it finds, unless the setting
/// `pdfmdCommand` names one: then that one, whatever its version.
///
/// Everything is asked of a login shell, because an app started from the Dock has almost no PATH: `whence -ap pdfmd` lists every
/// `pdfmd` on the shell's PATH, `alias pdfmd` the terminal's own alias.
enum PdfmdTool {
    struct Found: Codable {
        let command: String   // as a shell runs it
        let version: String
        let shown: String     // where it is, for people: a path with ~, or the alias's command
    }

    struct Resolved: Codable {
        var best: Found?
        var others: [Found] = []
        var explicit = false
        var failedCommand: String?   // the setting names something that does not answer
    }

    static var setting: String { Settings.string("pdfmdCommand").trimmingCharacters(in: .whitespacesAndNewlines) }

    /// Numeric order of versions ("3.10.0" is newer than "3.9.9").
    static func newer(_ a: String, than b: String) -> Bool {
        func parts(_ v: String) -> [Int] { v.split(whereSeparator: { !$0.isNumber }).compactMap { Int($0) } }
        let x = parts(a), y = parts(b)
        for i in 0..<max(x.count, y.count) {
            let p = i < x.count ? x[i] : 0, q = i < y.count ? y[i] : 0
            if p != q { return p > q }
        }
        return false
    }

    /// Every pdfmd command the shell knows, the alias first.
    static func candidates(timeout: Double = 8) -> [(command: String, shown: String)] {
        let out = run("alias pdfmd 2>/dev/null; whence -ap pdfmd 2>/dev/null", command: "", interactive: true, timeout: timeout)
        var list: [(String, String)] = []
        var seen = Set<String>()
        let home = NSHomeDirectory()
        for raw in out.split(separator: "\n") {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("pdfmd=") {
                var cmd = String(line.dropFirst("pdfmd=".count))
                if cmd.count >= 2, cmd.hasPrefix("'"), cmd.hasSuffix("'") { cmd = String(cmd.dropFirst().dropLast()) }
                if !cmd.isEmpty, seen.insert(cmd).inserted { list.append((cmd, cmd)) }
            } else if line.hasPrefix("/") {
                let real = (line as NSString).resolvingSymlinksInPath
                guard seen.insert(real).inserted else { continue }
                let shown = line.hasPrefix(home) ? "~" + line.dropFirst(home.count) : line
                list.append(("'" + line.replacingOccurrences(of: "'", with: "'\\''") + "'", shown))
            }
        }
        return list
    }

    /// Runs `command --version` and reads the number out of the answer (nil when it does not answer with one).
    static func probe(_ command: String, timeout: Double = 8) -> String? {
        let out = run("eval \"$PDFMD_CMD --version\" 2>&1", command: command, interactive: false, timeout: timeout)
        return out.range(of: #"\d+\.\d+\.\d+\S*"#, options: .regularExpression).map { String(out[$0]) }
    }

    /// The setting if it is set, else the newest of what is found (a tie goes to the one found first: the alias, the checkout).
    static func resolve(explicit: String? = nil) -> Resolved {
        let named = (explicit ?? setting).trimmingCharacters(in: .whitespacesAndNewlines)
        if !named.isEmpty {
            guard let v = probe(named) else { return Resolved(best: nil, others: [], explicit: true, failedCommand: named) }
            return Resolved(best: Found(command: named, version: v, shown: named), others: [], explicit: true, failedCommand: nil)
        }
        var found: [Found] = []
        for c in candidates() {
            if let v = probe(c.command) { found.append(Found(command: c.command, version: v, shown: c.shown)) }
        }
        var best: Found?
        for f in found where best == nil || newer(f.version, than: best!.version) { best = f }
        return Resolved(best: best, others: found.filter { $0.command != best?.command }, explicit: false, failedCommand: nil)
    }

    private static let lock = NSLock()
    private static var cache: (when: Date, setting: String, resolved: Resolved)?

    /// How long an answer is kept (`toolCacheSeconds`).
    private static var keep: Double { Settings.number("toolCacheSeconds") }

    private struct OnDisk: Codable { let when: Date; let setting: String; let resolved: Resolved }
    private static var cacheFile: URL {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("io.github.aliperdehan.pdfmdedit/pdfmd-found.json")
    }

    /// `resolve()` remembered (it starts a shell and runs every pdfmd: about two seconds), in memory and in a file, so that the
    /// command line (`colophon render`, a new process every time) does not ask again; forgotten when the setting changes.
    /// The app asks once at launch, so the About box opens at once.
    static func cachedResolve() -> Resolved {
        lock.lock(); defer { lock.unlock() }
        if let c = cache, c.setting == setting, Date().timeIntervalSince(c.when) < keep { return c.resolved }
        if let data = try? Data(contentsOf: cacheFile), let d = try? JSONDecoder().decode(OnDisk.self, from: data),
           d.setting == setting, Date().timeIntervalSince(d.when) < keep {
            cache = (d.when, d.setting, d.resolved)
            return d.resolved
        }
        let r = resolve()
        let now = Date()
        cache = (now, setting, r)
        if r.best != nil, let data = try? JSONEncoder().encode(OnDisk(when: now, setting: setting, resolved: r)) {
            try? FileManager.default.createDirectory(at: cacheFile.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? data.write(to: cacheFile, options: .atomic)
        }
        return r
    }

    /// Where programs are, for `colophon check`: the first of each name on the login shell's PATH.
    static func locate(_ names: [String]) -> [String: String] {
        let out = run(names.map { "print -r -- \($0)=$(whence -p \($0) 2>/dev/null)" }.joined(separator: "; "), command: "", interactive: true, timeout: 8)
        var found: [String: String] = [:]
        for line in out.split(separator: "\n") {
            let parts = line.split(separator: "=", maxSplits: 1).map(String.init)
            if parts.count == 2, parts[1].hasPrefix("/") { found[parts[0]] = parts[1] }
        }
        return found
    }

    /// The first line of `program --version`, for `colophon check`.
    static func versionLine(_ path: String) -> String {
        let out = run("\"$PDFMD_CMD\" --version 2>&1 | head -1", command: path, interactive: false, timeout: 8)
        return out.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static var pandocCache: (when: Date, setting: String, path: String?)?

    /// The pandoc the live preview runs (the setting `pandocCommand`, a path; else the first `pandoc` on the login shell's PATH), as an
    /// absolute path. Cached like `cachedResolve`; the first answer starts a shell, so not on the main thread.
    static func pandoc() -> String? {
        let named = Settings.string("pandocCommand").trimmingCharacters(in: .whitespacesAndNewlines)
        lock.lock(); defer { lock.unlock() }
        if let c = pandocCache, c.setting == named, Date().timeIntervalSince(c.when) < keep { return c.path }
        var path: String?
        if !named.isEmpty {
            let expanded = (named as NSString).expandingTildeInPath
            path = FileManager.default.isExecutableFile(atPath: expanded) ? expanded : nil
        } else {
            let out = run("whence -p pandoc 2>/dev/null", command: "", interactive: true, timeout: 8)
            path = out.split(separator: "\n").map { $0.trimmingCharacters(in: .whitespaces) }.first { $0.hasPrefix("/") }
        }
        pandocCache = (Date(), named, path)
        return path
    }

    /// The one line the About box shows: which pdfmd Colophon uses.
    static func aboutHead() -> String {
        let r = cachedResolve()
        if r.failedCommand != nil { return "pdfmd: the command in Settings does not answer" }
        guard let best = r.best else { return "pdfmd: not found" }
        return "pdfmd \(best.version)"
    }

    /// What "more" shows: which pdfmd, how it was chosen, where it is, and every other one that was found.
    static func detailLines() -> [String] {
        let r = cachedResolve()
        if let failed = r.failedCommand { return ["The pdfmd command in Settings does not answer:", failed, "", "Settings, General, pdfmd command (empty = the newest found)."] }
        guard let best = r.best else { return ["No pdfmd was found on the login shell's PATH or as its alias.", "", "Name its command in Settings, General, pdfmd command."] }
        var lines = ["pdfmd \(best.version)" + (r.explicit ? "  (named in Settings)" : "  (the newest found)"), best.shown]
        if !r.others.isEmpty {
            lines.append("")
            lines.append("Also found:")
            for o in r.others { lines.append("  \(o.version)  \(o.shown)") }
        }
        lines.append("")
        lines.append(r.explicit ? "Settings, General, pdfmd command is set; empty it to use the newest found." : "Settings, General, pdfmd command names one explicitly.")
        return lines
    }

    static func run(_ script: String, command: String, interactive: Bool, timeout: Double) -> String {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/zsh")
        p.arguments = [interactive ? "-lic" : "-lc", script]
        var env = ProcessInfo.processInfo.environment
        env["PDFMD_CMD"] = command
        p.environment = env
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = FileHandle.nullDevice
        p.standardInput = FileHandle.nullDevice
        do { try p.run() } catch { return "" }
        var data = Data()
        let done = DispatchSemaphore(value: 0)
        DispatchQueue.global().async { data = pipe.fileHandleForReading.readDataToEndOfFile(); done.signal() }
        let deadline = Date().addingTimeInterval(timeout)
        while p.isRunning, Date() < deadline { Thread.sleep(forTimeInterval: 0.02) }
        if p.isRunning { p.terminate() }
        _ = done.wait(timeout: .now() + 1)
        return String(decoding: data, as: UTF8.self)
    }
}
