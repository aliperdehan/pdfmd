import Foundation

/// `pdfmd --serve FOLDER` started by the app for one web studio window: the page of the studio then runs on the real folder, through the
/// JSON core of pdfmd (the app holds no logic of its own). pdfmd is found the way the build finds it (the Settings command, else the newest
/// one the login shell knows) and is run in a login shell; the one JSON line it prints says where it listens. Stopped with everything it
/// started when the window closes and when the app quits (a crashed app leaves it idle on its random port, which only the token opens).
final class StudioServer {
    struct Failure: Error { let message: String }

    let folder: URL
    private var process: Process?
    private let guardProcess = NSLock()
    /// The shell that was started (kept after `stop`, for the self-test).
    private(set) var lastPid: pid_t?

    init(folder: URL) { self.folder = folder }

    /// The project folder of a file: its own folder, or the folder above it when it sits in `parts/` (pdfmd builds a file of `parts/` as a part
    /// of the report beside that folder).
    static func projectFolder(of file: URL) -> URL {
        let dir = file.deletingLastPathComponent()
        return dir.lastPathComponent == "parts" ? dir.deletingLastPathComponent() : dir
    }

    /// The first JSON object among the lines pdfmd printed, as `url`; a login shell may print other things before it.
    static func announced(in text: String) -> URL? {
        for line in text.split(whereSeparator: \.isNewline) where line.hasPrefix("{") {
            if let data = line.data(using: .utf8), let o = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let s = o["url"] as? String, let u = URL(string: s) { return u }
        }
        return nil
    }

    /// Starts the server; `done` (on the main thread) gets the page's URL, or why there is none. `commandOverride` is for the self-test.
    func start(commandOverride: String? = nil, done: @escaping (Result<URL, Failure>) -> Void) {
        DispatchQueue.global().async { [self] in
            let found = commandOverride == nil ? PdfmdTool.cachedResolve() : nil
            guard let command = commandOverride ?? found?.best?.command else {
                let why = found?.failedCommand.map { "the pdfmd command in Settings does not answer: \($0)" } ?? "pdfmd was not found (name its command in Settings, General)"
                DispatchQueue.main.async { done(.failure(Failure(message: why))) }
                return
            }
            launch(command: command, done: done)
        }
    }

    private func launch(command: String, done: @escaping (Result<URL, Failure>) -> Void) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/zsh")
        p.arguments = ["-lic", #"eval "$PDFMD_CMD --serve \"\$@\"""#, "pdfmd", folder.path]
        var env = ProcessInfo.processInfo.environment
        env["PDFMD_CMD"] = command
        p.environment = env
        p.currentDirectoryURL = folder
        let out = Pipe(), err = Pipe()
        p.standardOutput = out
        p.standardError = err
        p.standardInput = FileHandle.nullDevice
        let lock = NSLock()
        var printed = "", complained = "", answered = false
        func answer(_ r: Result<URL, Failure>) {
            lock.lock(); let first = !answered; answered = true; lock.unlock()
            if first { DispatchQueue.main.async { done(r) } }
        }
        out.fileHandleForReading.readabilityHandler = { h in
            let chunk = h.availableData
            guard !chunk.isEmpty else { return }
            lock.lock(); printed += String(decoding: chunk, as: UTF8.self); let text = printed; lock.unlock()
            if let u = StudioServer.announced(in: text) { answer(.success(u)) }
        }
        err.fileHandleForReading.readabilityHandler = { h in
            let chunk = h.availableData
            guard !chunk.isEmpty else { return }
            lock.lock(); complained += String(decoding: chunk, as: UTF8.self); lock.unlock()
        }
        p.terminationHandler = { proc in
            out.fileHandleForReading.readabilityHandler = nil
            err.fileHandleForReading.readabilityHandler = nil
            lock.lock(); let said = (complained.isEmpty ? printed : complained).trimmingCharacters(in: .whitespacesAndNewlines); lock.unlock()
            answer(.failure(Failure(message: "pdfmd --serve ended (status \(proc.terminationStatus)) before it said where it listens:\n\(said)")))
        }
        do { try p.run() } catch {
            answer(.failure(Failure(message: "could not start pdfmd: \(error.localizedDescription)")))
            return
        }
        guardProcess.lock(); process = p; lastPid = p.processIdentifier; guardProcess.unlock()
        let wait = Settings.number("studioServerTimeout")
        if wait > 0 {
            DispatchQueue.global().asyncAfter(deadline: .now() + wait) {
                lock.lock(); let late = !answered; lock.unlock()
                guard late, p.isRunning else { return }
                answer(.failure(Failure(message: "pdfmd --serve did not say where it listens within \(Int(wait)) s (Settings > Studio). Its older versions have no --serve: it needs pdfmd 3.32.36 or newer.")))
                PdfmdBuild.killTree(p.processIdentifier)
            }
        }
    }

    /// Stops the server and everything it started.
    func stop() {
        guardProcess.lock(); let p = process; process = nil; guardProcess.unlock()
        guard let p, p.isRunning else { return }
        PdfmdBuild.killTree(p.processIdentifier)
    }
}
