import Foundation

/// Where the TeX engines and helpers live. An app started from Finder gets launchd's bare PATH (no TeX, no Homebrew), so tools are
/// looked up by absolute path and the children get an explicit PATH. (pdfmd is different: it is found and started the way a build
/// does it, through the login shell, see `PdfmdTool`.)
enum PopToolchain {
    private static let lock = NSLock()
    private static var cache: [String: String?] = [:]

    static let searchDirs: [String] = {
        let fm = FileManager.default
        var dirs = ["/Library/TeX/texbin", "/opt/homebrew/bin", "/usr/local/bin",
                    fm.homeDirectoryForCurrentUser.appendingPathComponent(".local/bin").path]
        let texlive = URL(fileURLWithPath: "/usr/local/texlive")
        for year in ((try? fm.contentsOfDirectory(atPath: texlive.path)) ?? []).sorted().reversed() {
            let bin = texlive.appendingPathComponent(year).appendingPathComponent("bin")
            for arch in (try? fm.contentsOfDirectory(atPath: bin.path)) ?? [] {
                dirs.append(bin.appendingPathComponent(arch).path)
            }
        }
        return dirs + ["/usr/bin", "/bin"]
    }()

    static func find(_ name: String) -> String? {
        lock.lock(); defer { lock.unlock() }
        if let hit = cache[name] { return hit }
        let found = searchDirs.map { $0 + "/" + name }.first { FileManager.default.isExecutableFile(atPath: $0) }
        cache[name] = .some(found)
        return found
    }

    /// The pdfmd to run, as a shell command (the `pdfmdCommand` setting, else the newest pdfmd the login shell knows).
    static func pdfmdCommand() -> String? { PdfmdTool.cachedResolve().best?.command }

    /// The environment for a child process: ours, with PATH replaced by the search directories.
    static var environment: [String: String] {
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = searchDirs.joined(separator: ":")
        return env
    }

    /// Runs a helper to its end and returns its exit status (nil if it could not start).
    static func run(_ exe: String, _ args: [String]) -> Int32? {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: exe)
        p.arguments = args
        p.environment = environment
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        guard (try? p.run()) != nil else { return nil }
        p.waitUntilExit()
        return p.terminationStatus
    }
}
