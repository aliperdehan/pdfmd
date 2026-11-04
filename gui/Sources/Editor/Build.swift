import Cocoa

/// One run of pdfmd on a file: the command that `PdfmdTool` found, in a login shell (so that pandoc, the TeX tools and the author's
/// own PATH are there, which an app started from the Dock does not have), in the file's folder. The file and the extra words are
/// handed over as arguments of the shell, never spliced into the script, so a path with a quote in it stays a path.
enum PdfmdBuild {
    struct Result {
        var status: Int32 = 0
        var output = ""
        var made: URL?            // the file pdfmd says it wrote
        var seconds = 0.0
        var timedOut = false
        var couldNotStart: String?
        var ok: Bool { status == 0 && !timedOut && couldNotStart == nil }
    }

    /// The file named by pdfmd's own report line, `OK    a.md > a.pdf  in 18.7 s  (lualatex)`. The name is beside the source the line names,
    /// which is not always the file that was built: a file of `parts/` is built as part of `../report.md`, and the line says
    /// `OK    ../report.md > report.results.pdf`, so the PDF is in the folder above. Looked for there first, then in the folder it ran in;
    /// without a line, the same name with `.pdf` if that exists.
    static func madeFile(output: String, source: URL) -> URL? {
        let folder = source.deletingLastPathComponent()
        var named: (source: String, output: String)?
        for line in output.split(whereSeparator: \.isNewline) {
            guard line.hasPrefix("OK"), let range = line.range(of: " > ") else { continue }
            var rest = line[range.upperBound...]
            if let end = rest.range(of: #"\s+in \d"#, options: .regularExpression) { rest = rest[..<end.lowerBound] }
            let name = rest.trimmingCharacters(in: .whitespaces)
            if !name.isEmpty { named = (line[line.index(line.startIndex, offsetBy: 2)..<range.lowerBound].trimmingCharacters(in: .whitespaces), name) }
        }
        if let named {
            func resolve(_ path: String, in base: URL) -> URL { path.hasPrefix("/") ? URL(fileURLWithPath: path) : URL(fileURLWithPath: path, relativeTo: base).standardizedFileURL }
            let beside = named.source.isEmpty ? folder : resolve(named.source, in: folder).deletingLastPathComponent()
            for base in [beside, folder] {
                let url = resolve(named.output, in: base)
                if FileManager.default.fileExists(atPath: url.path) { return url }
            }
        }
        let same = source.deletingPathExtension().appendingPathExtension("pdf")
        return FileManager.default.fileExists(atPath: same.path) ? same : nil
    }

    /// Starts the build; `output` gets pieces of what pdfmd prints while it runs, `done` the result. Both are called on the main thread.
    @discardableResult
    static func run(command: String, arguments: String, file: URL, extra: [String] = [], timeout: Double, output: @escaping (String) -> Void,
                    done: @escaping (Result) -> Void) -> Process {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/zsh")
        // `extra` (an export's `-t docx -o OUT`) follows the file as arguments of the shell, never inside the script: a path with a quote stays a path
        p.arguments = ["-lic", #"eval "$PDFMD_CMD $PDFMD_ARGS \"\$@\"""#, "pdfmd", file.path] + extra
        var env = ProcessInfo.processInfo.environment
        env["PDFMD_CMD"] = command
        env["PDFMD_ARGS"] = arguments
        p.environment = env
        p.currentDirectoryURL = file.deletingLastPathComponent()
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        p.standardInput = FileHandle.nullDevice
        let lock = NSLock()
        var collected = Data()
        var timedOut = false
        let started = Date()
        pipe.fileHandleForReading.readabilityHandler = { handle in
            let chunk = handle.availableData
            guard !chunk.isEmpty else { return }
            lock.lock(); collected.append(chunk); lock.unlock()
            let text = String(decoding: chunk, as: UTF8.self)
            DispatchQueue.main.async { output(text) }
        }
        p.terminationHandler = { proc in
            pipe.fileHandleForReading.readabilityHandler = nil
            let rest = pipe.fileHandleForReading.readDataToEndOfFile()
            lock.lock(); collected.append(rest); let all = collected; let stopped = timedOut; lock.unlock()
            if !rest.isEmpty { let text = String(decoding: rest, as: UTF8.self); DispatchQueue.main.async { output(text) } }
            let text = String(decoding: all, as: UTF8.self)
            var result = Result(status: proc.terminationStatus, output: text, seconds: Date().timeIntervalSince(started), timedOut: stopped)
            if result.ok { result.made = madeFile(output: text, source: file) }
            DispatchQueue.main.async { done(result) }
        }
        do {
            try p.run()
        } catch {
            DispatchQueue.main.async { done(Result(status: -1, couldNotStart: "\(error.localizedDescription)")) }
            return p
        }
        if timeout > 0 {
            DispatchQueue.global().asyncAfter(deadline: .now() + timeout) {
                guard p.isRunning else { return }
                lock.lock(); timedOut = true; lock.unlock()
                killTree(p.processIdentifier)
            }
        }
        return p
    }

    /// The process and everything it started (a build runs python, pandoc and lualatex below the shell), the newest first.
    static func killTree(_ pid: pid_t) {
        func children(of pid: pid_t) -> [pid_t] {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
            p.arguments = ["-P", String(pid)]
            let pipe = Pipe()
            p.standardOutput = pipe
            p.standardError = FileHandle.nullDevice
            guard (try? p.run()) != nil else { return [] }
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            p.waitUntilExit()
            return String(decoding: data, as: UTF8.self).split(whereSeparator: \.isNewline).compactMap { pid_t($0) }
        }
        func order(_ pid: pid_t) -> [pid_t] { children(of: pid).flatMap(order) + [pid] }
        for target in order(pid) { kill(target, SIGTERM) }
    }

    /// A pdfmd that is already rebuilding this file on every save (`pdfmd -w FILE`, or the watcher that `pdfmd --edit --editor` starts):
    /// building again beside it would run two TeX builds on the same files. The command line of the process, or nil.
    static func watcher(for file: URL, listing: String? = nil) -> String? {
        var text = listing ?? ""
        if listing == nil {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: "/bin/ps")
            p.arguments = ["-axww", "-o", "command="]
            let pipe = Pipe()
            p.standardOutput = pipe
            p.standardError = FileHandle.nullDevice
            guard (try? p.run()) != nil else { return nil }
            text = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
            p.waitUntilExit()
        }
        let name = file.lastPathComponent
        for raw in text.split(whereSeparator: \.isNewline) {
            let line = String(raw)
            guard line.contains("pdfmd"), line.contains(name) else { continue }
            let words = line.split(separator: " ").map(String.init)
            if words.contains("--watch") || words.contains("-w") || words.contains(where: { $0.hasPrefix("--watch=") }) { return line }
        }
        return nil
    }
}

/// The build log: what pdfmd printed, in a small window of its own that does not take the keyboard from the editor.
final class BuildLogWindow {
    let panel: NSPanel
    private let text = NSTextView()

    init() {
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 640, height: 320),
                        styleMask: [.titled, .closable, .resizable, .utilityWindow], backing: .buffered, defer: true)
        panel.isReleasedWhenClosed = false
        panel.becomesKeyOnlyIfNeeded = true
        panel.hidesOnDeactivate = false
        panel.setFrameAutosaveName("pdfmdedit.buildlog")
        let scroll = NSScrollView(frame: panel.contentView!.bounds)
        scroll.autoresizingMask = [.width, .height]
        scroll.hasVerticalScroller = true
        text.isEditable = false
        text.isRichText = false
        text.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        text.textContainerInset = NSSize(width: 6, height: 6)
        text.autoresizingMask = [.width]
        text.isVerticallyResizable = true
        text.textContainer?.widthTracksTextView = true
        scroll.documentView = text
        panel.contentView = scroll
    }

    var string: String { text.string }

    func reset(title: String, header: String) {
        panel.title = title
        text.string = header
    }

    func append(_ piece: String) {
        text.textStorage?.append(NSAttributedString(string: piece, attributes: [
            .font: NSFont.monospacedSystemFont(ofSize: 11, weight: .regular), .foregroundColor: NSColor.labelColor]))
        text.scrollToEndOfDocument(nil)
    }

    func show() { panel.orderFront(nil) }
}

/// What command R does in an editor window: save the file, run pdfmd on it, and show the PDF it made. One build at a time; a command R
/// pressed while one runs is remembered and builds again when that one ends (the text may have changed since).
final class BuildController: NSObject {
    weak var owner: EditorWindowController?
    private(set) var running = false
    private var queued = false
    private(set) var builds = 0
    private(set) var lastResult: PdfmdBuild.Result?
    private var process: Process?
    private var showsBuildStatus = false
    let log = BuildLogWindow()

    /// For the self-test: a replacement for "the pdfmd that was found" and for what happens to the PDF.
    var commandOverride: String?
    var onFinished: ((PdfmdBuild.Result) -> Void)?
    var displayWindows = true   // false in the self-test: a window made by hand and never shown

    private var editorDocument: EditorDocument? { owner?.document as? EditorDocument }

    private func say(_ s: String, status: Bool = true) {
        owner?.window?.subtitle = s
        showsBuildStatus = status && !s.isEmpty
    }

    /// The text was edited: a "built in 3 s" is about the old text, a failure stays until the next build.
    func textEdited() {
        guard showsBuildStatus, lastResult?.ok != false, !running else { return }
        say("", status: false)
    }

    // MARK: asking for a build

    func request() {
        guard let doc = editorDocument else { return }
        if owner?.exporter.running == true {
            say("Exporting… build when it ends", status: false)
            NSSound.beep()
            return
        }
        if running {
            queued = true
            say("Building… (the next build is queued)")
            return
        }
        if doc.fileURL == nil || doc.isDocumentEdited {
            doc.save(withDelegate: self, didSave: #selector(document(_:didSave:contextInfo:)), contextInfo: nil)   // asks where, if untitled
        } else {
            start()
        }
    }

    @objc func document(_ doc: NSDocument, didSave: Bool, contextInfo: UnsafeMutableRawPointer?) {
        guard didSave else { return }
        start()
    }

    private func start() {
        guard let doc = editorDocument, let url = doc.fileURL else { return }
        if !Settings.flag("buildWhenWatched"), let other = PdfmdBuild.watcher(for: url) {
            say("Saved. pdfmd is watching this file and rebuilds it by itself")
            log.reset(title: "Build log: \(url.lastPathComponent)", header: "Saved. Not building: this pdfmd is already rebuilding the file on every save:\n\(other)\n(Settings > Build > Build although pdfmd is watching)\n")
            return
        }
        running = true
        say("Building…")
        log.reset(title: "Build log: \(url.lastPathComponent)", header: "")
        let override = commandOverride
        DispatchQueue.global().async { [weak self] in
            // the first answer starts a shell: not on the main thread
            let found = override == nil ? PdfmdTool.cachedResolve() : nil
            let command = override ?? found?.best?.command
            let failed = found?.failedCommand
            DispatchQueue.main.async { self?.launch(command: command, failed: failed, file: url) }
        }
    }

    private func launch(command: String?, failed: String?, file: URL) {
        guard let command else {
            var r = PdfmdBuild.Result(status: -1)
            r.couldNotStart = failed.map { "the pdfmd command in Settings does not answer: \($0)" }
                ?? "pdfmd was not found (name its command in Settings, General)"
            finish(r, file: file)
            return
        }
        let words = Settings.string("buildArguments").trimmingCharacters(in: .whitespacesAndNewlines)
        log.append("$ \(command) \(words) \(file.lastPathComponent)\n")
        process = PdfmdBuild.run(command: command, arguments: words, file: file, timeout: Settings.number("buildTimeout"),
                                 output: { [weak self] in self?.log.append($0) }, done: { [weak self] in self?.finish($0, file: file) })
    }

    // MARK: the end

    private func finish(_ r: PdfmdBuild.Result, file: URL) {
        running = false
        process = nil
        builds += 1
        lastResult = r
        let seconds = String(format: "%.1f", r.seconds)
        if r.ok {
            let name = r.made?.lastPathComponent
            say(name.map { "Built \($0) in \(seconds) s" } ?? "Built in \(seconds) s")
            if let made = r.made { showMade(made) }
        } else {
            let why = r.couldNotStart ?? (r.timedOut ? "stopped after \(Settings.int("buildTimeout")) s" : "exit status \(r.status)")
            say("Build failed (\(why)). View > Show Build Log")
            if let problem = r.couldNotStart { log.append(problem + "\n") }
            if r.timedOut { log.append("\nStopped: the build ran for more than \(Settings.int("buildTimeout")) s (Settings > Build).\n") }
            if displayWindows { log.show() }
        }
        onFinished?(r)
        if queued {
            queued = false
            request()
        }
    }

    /// The file that was made: an open window of it shows it again (once: nothing happens when the automatic reload was quicker),
    /// otherwise it is opened, if the setting says so, and the keyboard stays in the editor.
    private func showMade(_ made: URL) {
        if made.pathExtension.lowercased() == "pdf", let studio = owner?.studio, studio.isShown {
            studio.showBuilt(made)   // the pane beside the text shows it: no window of its own
            return
        }
        let target = made.resolvingSymlinksInPath().standardizedFileURL
        let controller = NSDocumentController.shared
        if let open = controller.documents.first(where: { $0.fileURL?.resolvingSymlinksInPath().standardizedFileURL == target }) as? PDFViewerDocument {
            open.reloadIfChanged()
            return
        }
        guard made.pathExtension.lowercased() == "pdf", Settings.flag("buildOpensPDF") else { return }
        let editor = owner?.window
        let show = displayWindows
        controller.openDocument(withContentsOf: made, display: show) { doc, _, error in
            if let error { NSApp.presentError(error); return }
            if !show { if let doc, doc.windowControllers.isEmpty { doc.makeWindowControllers() }; return }
            editor?.makeKeyAndOrderFront(nil)
        }
    }

    func showLog() { log.show() }
    var hasLog: Bool { !log.string.isEmpty }
}
