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

    /// Runs a helper on the caller's worker queue, bounded by the popup's existing TeX/toolchain limit.
    struct Timeout: LocalizedError {
        let converter: String
        let seconds: Double
        var errorDescription: String? {
            "\(converter) stopped after \(Settings.formatNumber(seconds)) s (Settings > Popup > TeX time limit)."
        }
    }

    static func run(_ exe: String, _ args: [String]) throws -> Int32? {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: exe)
        p.arguments = args
        p.environment = environment
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        let ended = DispatchSemaphore(value: 0)
        p.terminationHandler = { _ in ended.signal() }
        guard (try? p.run()) != nil else { return nil }
        let limit = Settings.number("popTimeoutS")
        if ended.wait(timeout: .now() + limit) == .timedOut {
            if p.isRunning { PdfmdBuild.killTree(p.processIdentifier, grace: Settings.number("buildStopGrace")) }
            ended.wait() // the tree is sent SIGKILL after the existing build-stop grace if SIGTERM was ignored
            throw Timeout(converter: URL(fileURLWithPath: exe).lastPathComponent, seconds: limit)
        }
        return p.terminationStatus
    }
}
