import Cocoa

/// What File > Export As does in an editor window: save the document if it is new or edited (pdfmd needs its folder, for the metadata and
/// the pictures beside it), ask where the file goes, run pdfmd with the words of the chosen format, say how it went. It shares the run
/// code (`PdfmdBuild`) and the log window with a build but nothing else: an exported PDF is not "the last build", so it never lands in the
/// preview pane or opens by itself.
final class ExportController: NSObject {
    weak var owner: EditorWindowController?
    private(set) var running = false
    private(set) var exports = 0
    private(set) var lastResult: PdfmdBuild.Result?
    private(set) var lastOutput: URL?
    private var pending: ExportFormat?
    private var process: Process?
    private var showsStatus = false

    /// For the self-test: a replacement for "the pdfmd that was found", for the Save panel, and a way to see the end.
    var commandOverride: String?
    var chooseOutput: ((ExportFormat, URL) -> URL?)?
    var onFinished: ((PdfmdBuild.Result, URL?) -> Void)?
    var displayWindows = true

    private var document: EditorDocument? { owner?.document as? EditorDocument }

    private func say(_ s: String, status: Bool = true) {
        owner?.window?.subtitle = s
        showsStatus = status && !s.isEmpty
    }

    /// The text was edited: "Exported a.docx" is about the old text.
    func textEdited() {
        guard showsStatus, lastResult?.ok != false, !running else { return }
        say("", status: false)
    }

    // MARK: asking

    func start(_ format: ExportFormat) {
        guard let doc = document else { return }
        if running || owner?.builder.running == true {
            say(running ? "Exporting… wait until it ends" : "Building… export when it ends", status: false)
            NSSound.beep()
            return
        }
        if doc.fileURL == nil || doc.isDocumentEdited {
            pending = format
            doc.save(withDelegate: self, didSave: #selector(document(_:didSave:contextInfo:)), contextInfo: nil)   // asks where, if untitled
        } else {
            choose(format)
        }
    }

    @objc func document(_ doc: NSDocument, didSave: Bool, contextInfo: UnsafeMutableRawPointer?) {
        let format = pending
        pending = nil
        guard didSave, let format else { return }
        choose(format)
    }

    private func choose(_ format: ExportFormat) {
        guard let source = document?.fileURL else { return }
        let proposed = source.deletingLastPathComponent().appendingPathComponent(format.fileName(for: source))
        if let chooseOutput {
            if let out = chooseOutput(format, proposed) { run(format, source: source, out: out) }
            return
        }
        let panel = NSSavePanel()
        panel.title = "Export as \(format.panelTitle)"
        let pictures = format.path.last == "Pictures" || ["png-cropped", "svg-cropped"].contains(format.id)
        panel.message = "pdfmd " + format.words.joined(separator: " ") + (pictures ? "   (a document of several pages makes a folder of numbered pictures, named like this file)" : "")
        panel.directoryURL = source.deletingLastPathComponent()
        panel.nameFieldStringValue = proposed.lastPathComponent
        panel.canCreateDirectories = true
        panel.isExtensionHidden = false
        panel.allowsOtherFileTypes = true
        guard let window = owner?.window else { return }
        panel.beginSheetModal(for: window) { [weak self] answer in
            guard answer == .OK, let out = panel.url else { return }
            self?.run(format, source: source, out: out)
        }
    }

    // MARK: running

    private func run(_ format: ExportFormat, source: URL, out: URL) {
        if out.standardizedFileURL.resolvingSymlinksInPath() == source.standardizedFileURL.resolvingSymlinksInPath() {
            say("Not exported: that would overwrite the document itself", status: false)
            NSSound.beep()
            return
        }
        running = true
        say("Exporting \(out.lastPathComponent)…")
        let log = owner?.builder.log
        log?.reset(title: "Export log: \(out.lastPathComponent)", header: "")
        let started = Date()
        let override = commandOverride
        DispatchQueue.global().async { [weak self] in
            let found = override == nil ? PdfmdTool.cachedResolve() : nil
            let command = override ?? found?.best?.command
            DispatchQueue.main.async { self?.launch(format, command: command, failed: found?.failedCommand, source: source, out: out, started: started) }
        }
    }

    private func launch(_ format: ExportFormat, command: String?, failed: String?, source: URL, out: URL, started: Date) {
        guard let command else {
            var r = PdfmdBuild.Result(status: -1)
            r.couldNotStart = failed.map { "the pdfmd command in Settings does not answer: \($0)" }
                ?? "pdfmd was not found (name its command in Settings, General)"
            finish(r, out: out, started: started)
            return
        }
        let mine = ExportArguments.withoutTarget(Settings.string("buildArguments"))
        let words = format.words + ["-o", out.path]
        owner?.builder.log.append("$ \(command) \(mine) \(source.lastPathComponent) \(words.joined(separator: " "))\n")
        process = PdfmdBuild.run(command: command, arguments: mine, file: source, extra: words, timeout: Settings.number("buildTimeout"),
                                 output: { [weak self] in self?.owner?.builder.log.append($0) }, done: { [weak self] in self?.finish($0, out: out, started: started) })
    }

    /// Done means: exit status 0, and the file is there and newer than the start (a stale file of an earlier export is not a success), or
    /// pdfmd's own `OK  a.md > a.docx` line names it (a picture format writes more than one file).
    /// A picture format of several pages makes a folder instead (pdfmd's `--page-folder`: `NAME/001.png`, `002.png` ...), named like the
    /// file without its extension; then that folder is what was made.
    static func made(_ r: PdfmdBuild.Result, out: URL, started: Date) -> URL? {
        guard r.ok else { return nil }
        let folder = out.deletingPathExtension()
        func fresh(_ url: URL) -> Bool {
            guard let date = (try? FileManager.default.attributesOfItem(atPath: url.path))?[.modificationDate] as? Date else { return false }
            return date >= started.addingTimeInterval(-2)
        }
        var named = false
        for line in r.output.split(whereSeparator: \.isNewline) where line.hasPrefix("OK") {
            if line.contains(out.lastPathComponent) { named = true }
            if line.contains(folder.lastPathComponent + "/") { named = true }
        }
        if FileManager.default.fileExists(atPath: out.path), named || fresh(out) { return out }
        var isDir: ObjCBool = false
        if FileManager.default.fileExists(atPath: folder.path, isDirectory: &isDir), isDir.boolValue, named || fresh(folder) { return folder }
        return nil
    }

    private func finish(_ r: PdfmdBuild.Result, out: URL, started: Date) {
        running = false
        process = nil
        exports += 1
        lastResult = r
        let log = owner?.builder.log
        let seconds = String(format: "%.1f", r.seconds)
        if let made = Self.made(r, out: out, started: started) {
            lastOutput = made
            let isFolder = made != out
            say("Exported \(made.lastPathComponent)\(isFolder ? "/ (one picture per page)" : "") in \(seconds) s")
            if Settings.flag("exportReveal"), displayWindows { NSWorkspace.shared.activateFileViewerSelecting([made]) }
        } else {
            lastOutput = nil
            let why = r.couldNotStart ?? (r.timedOut ? "stopped after \(Settings.int("buildTimeout")) s" : (r.ok ? "pdfmd wrote no file" : "exit status \(r.status)"))
            say("Export failed (\(why)). View > Show Build Log")
            if let problem = r.couldNotStart { log?.append(problem + "\n") }
            if r.timedOut { log?.append("\nStopped: the export ran for more than \(Settings.int("buildTimeout")) s (Settings > Build).\n") }
            if displayWindows { log?.show() }
        }
        onFinished?(r, lastOutput)
    }
}
