import Foundation
import CryptoKit

/// A compiled preamble. Loading packages is most of a render (a house-style package takes 2 s of 2.5), so the
/// document class, the packages and the preamble are dumped once into a TeX format (`mylatexformat`), and each
/// later render starts from it. Only pdflatex: a format made by lualatex stops on unicode-math, and xelatex is
/// untested. The cache is an optimisation only: a render that finds it missing, stale or broken runs the full
/// document, so it cannot change a result.
enum PopFormatCache {
    private static let lock = NSLock()
    private static var building = Set<String>()
    private static var failed = Set<String>()
    private static let queue = DispatchQueue(label: "pop.format", qos: .utility)
    private static var root: URL { PopStore.cacheDir.appendingPathComponent("formats", isDirectory: true) }

    private static func supports(_ e: PopEngine) -> Bool { e == .pdflatex }

    private static func key(_ r: PopRequest) -> String {
        let digest = SHA256.hash(data: Data((r.engine.rawValue + "\n" + PopWrapper.preambleText(r.preamble)).utf8))
        return digest.map { String(format: "%02x", $0) }.joined().prefix(24).description
    }

    private static func dir(_ r: PopRequest) -> URL { root.appendingPathComponent(key(r), isDirectory: true) }

    /// Files the preamble read from outside the TeX distribution (a package under ~/Library/texmf that its author
    /// edits) with their modification times, one "time path" per line, so an edit to one of them retires the format.
    private static func stamp(_ path: String) -> String {
        let real = URL(fileURLWithPath: path).resolvingSymlinksInPath().path
        let t = (try? FileManager.default.attributesOfItem(atPath: real)[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0
        return "\(Int(t)) \(path)"
    }

    /// The folder holding a format that is still valid for this request, or nil.
    static func ready(_ r: PopRequest) -> URL? {
        guard supports(r.engine) else { return nil }
        let d = dir(r)
        guard FileManager.default.fileExists(atPath: d.appendingPathComponent("pop.fmt").path),
              let deps = try? String(contentsOf: d.appendingPathComponent("deps.txt"), encoding: .utf8) else { return nil }
        for line in deps.split(separator: "\n") {
            let path = line.drop(while: { $0 != " " }).dropFirst()
            if stamp(String(path)) != String(line) { try? FileManager.default.removeItem(at: d); return nil }
        }
        return d
    }

    static func discard(_ r: PopRequest) { try? FileManager.default.removeItem(at: dir(r)) }

    /// Builds the format for `r` off the render path; at most one build at a time.
    static func buildInBackground(_ r: PopRequest) {
        guard supports(r.engine), ready(r) == nil else { return }
        let k = key(r)
        lock.lock()
        if building.isEmpty && !failed.contains(k) { building.insert(k) } else { lock.unlock(); return }
        lock.unlock()
        queue.async {
            let ok = build(r)
            lock.lock(); building.remove(k); if !ok { failed.insert(k) }; lock.unlock()
        }
    }

    /// For a one-shot process: wait for the build that a render started, or the process would end before it.
    static func waitIdle() {
        for _ in 0..<Int(Settings.number("popWarmWaitS") * 10) {
            lock.lock(); let idle = building.isEmpty; lock.unlock()
            if idle { return }
            Thread.sleep(forTimeInterval: 0.1)
        }
    }

    private static func build(_ r: PopRequest) -> Bool {
        guard let ini = PopToolchain.find("pdftex") else { return false }
        let fm = FileManager.default
        let work = fm.temporaryDirectory.appendingPathComponent("pop-fmt-" + UUID().uuidString, isDirectory: true)
        guard (try? fm.createDirectory(at: work, withIntermediateDirectories: true)) != nil else { return false }
        defer { try? fm.removeItem(at: work) }
        guard (try? PopWrapper.preambleText(r.preamble).write(to: work.appendingPathComponent("pre.tex"), atomically: true, encoding: .utf8)) != nil
        else { return false }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: ini)
        p.arguments = ["-ini", "-recorder", "-jobname=pop", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape",
                       "&pdflatex", "mylatexformat.ltx", "\"\"\"pre.tex\"\"\""]
        p.currentDirectoryURL = work
        p.environment = PopToolchain.environment
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        guard (try? p.run()) != nil else { return false }
        let killer = DispatchWorkItem { if p.isRunning { p.terminate() } }
        DispatchQueue.global().asyncAfter(deadline: .now() + Settings.number("popFormatTimeoutS"), execute: killer)
        p.waitUntilExit()
        killer.cancel()
        let fmt = work.appendingPathComponent("pop.fmt")
        guard p.terminationStatus == 0, fm.fileExists(atPath: fmt.path) else { return false }

        // what to watch: input files outside the TeX distribution
        let tree = (PopToolchain.find("kpsewhich")).flatMap { kpsewhich($0, "TEXMFDIST") }
        let fls = (try? String(contentsOf: work.appendingPathComponent("pop.fls"), encoding: .utf8)) ?? ""
        var watched: [String] = []
        for line in fls.split(separator: "\n") where line.hasPrefix("INPUT /") {
            let path = String(line.dropFirst(6))
            if let t = tree, path.hasPrefix(t) { continue }
            if path.hasPrefix("/usr/local/texlive/") || path.hasPrefix("/usr/share/texlive/") { continue }
            if !watched.contains(path) { watched.append(path) }
        }
        let dest = dir(r)
        try? fm.removeItem(at: dest)
        guard (try? fm.createDirectory(at: dest, withIntermediateDirectories: true)) != nil,
              (try? fm.moveItem(at: fmt, to: dest.appendingPathComponent("pop.fmt"))) != nil,
              (try? watched.map(stamp).joined(separator: "\n").write(to: dest.appendingPathComponent("deps.txt"), atomically: true, encoding: .utf8)) != nil
        else { return false }
        prune(keeping: dest)
        return true
    }

    private static func kpsewhich(_ exe: String, _ variable: String) -> String? {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: exe)
        p.arguments = ["-var-value", variable]
        p.environment = PopToolchain.environment
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = FileHandle.nullDevice
        guard (try? p.run()) != nil else { return nil }
        let out = pipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        let s = (String(data: out, encoding: .utf8) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return s.isEmpty ? nil : s
    }

    /// A format is about 9 MB: keep the newest few (`popFormatKeep`).
    private static func prune(keeping: URL) {
        let fm = FileManager.default
        let dirs = (try? fm.contentsOfDirectory(at: root, includingPropertiesForKeys: [.contentModificationDateKey])) ?? []
        let dated = dirs.map { ($0, (try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast) }
        for (d, _) in dated.sorted(by: { $0.1 > $1.1 }).dropFirst(max(1, Settings.int("popFormatKeep"))) where d != keeping { try? fm.removeItem(at: d) }
    }
}
