import Cocoa
import PDFKit
import WebKit

/// Words as a shell reads them (quotes and backslashes, a leading `~`), for the settings that hold extra command-line words.
func shellWords(_ text: String) -> [String] {
    var words: [String] = []
    var current = ""
    var quote: Character?
    var started = false
    var escaped = false
    for ch in text {
        if escaped { current.append(ch); escaped = false; continue }
        if ch == "\\" && quote != "'" { escaped = true; started = true; continue }
        if let q = quote {
            if ch == q { quote = nil } else { current.append(ch) }
        } else if ch == "'" || ch == "\"" {
            quote = ch; started = true
        } else if ch == " " || ch == "\t" || ch == "\n" {
            if started { words.append(current); current = ""; started = false }
        } else {
            current.append(ch); started = true
        }
    }
    if started { words.append(current) }
    return words.map { $0.hasPrefix("~") ? ($0 as NSString).expandingTildeInPath : $0 }
}

/// Markdown to a web page for the preview: pandoc run directly on the text of the window (saved or not), about a tenth of a second for a
/// page, where pdfmd's own HTML takes three seconds (Python's start-up and its discovery) and a PDF twenty. It is a preview: pandoc's
/// own Markdown, no pdfmd defaults, filters or fonts. Math is MathML, which WebKit draws itself.
enum HTMLRender {
    struct Output {
        var file: URL?
        var error = ""
        var seconds = 0.0
    }

    static var cacheFolder: URL {
        let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        return base.appendingPathComponent("io.github.aliperdehan.pdfmdedit/preview", isDirectory: true)
    }

    /// A short stable name for a file's preview (djb2 of its path).
    static func key(for url: URL?, fallback: String) -> String {
        guard let url else { return fallback }
        var h: UInt64 = 5381
        for b in url.standardizedFileURL.path.utf8 { h = (h &* 33) &+ UInt64(b) }
        return String(h, radix: 16)
    }

    static let builtInStyle = """
    :root { color-scheme: light dark; }
    body { font: 16px/1.55 -apple-system, "SF Pro Text", "Helvetica Neue", sans-serif; max-width: 46rem; margin: 2rem auto; padding: 0 1.4rem 4rem; }
    h1, h2, h3, h4 { line-height: 1.25; margin-top: 1.6em; }
    code, pre, kbd { font-family: ui-monospace, "JetBrains Mono", Menlo, monospace; font-size: 0.88em; }
    pre { background: color-mix(in srgb, currentColor 7%, transparent); padding: .7em 1em; border-radius: 6px; overflow-x: auto; }
    :not(pre) > code { background: color-mix(in srgb, currentColor 8%, transparent); padding: .1em .3em; border-radius: 4px; }
    table { border-collapse: collapse; margin: 1em 0; }
    th, td { border: 1px solid color-mix(in srgb, currentColor 30%, transparent); padding: .3em .7em; }
    img, svg { max-width: 100%; height: auto; }
    blockquote { border-left: 3px solid color-mix(in srgb, currentColor 35%, transparent); margin-left: 0; padding-left: 1em; opacity: .85; }
    hr { border: 0; border-top: 1px solid color-mix(in srgb, currentColor 25%, transparent); }
    header#title-block-header h1.title { margin-top: 0; }
    """

    private static var mathFlags: [String: String] = [:]
    private static let mathLock = NSLock()

    /// MathML for the formulas: `--math-method=mathml` in a recent pandoc, `--mathml` in an older one (a recent one warns about it on every run).
    static func mathFlag(_ pandoc: String) -> String {
        mathLock.lock(); defer { mathLock.unlock() }
        if let known = mathFlags[pandoc] { return known }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: pandoc)
        p.arguments = ["--help"]
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = FileHandle.nullDevice
        var flag = "--mathml"
        if (try? p.run()) != nil {
            let help = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
            p.waitUntilExit()
            if help.contains("--math-method") { flag = "--math-method=mathml" }
        }
        mathFlags[pandoc] = flag
        return flag
    }

    /// Renders on a background queue; `done` runs on the main thread.
    static func render(_ text: String, source: URL?, name: String, key: String, done: @escaping (Output) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            let started = Date()
            var out = Output()
            defer { out.seconds = Date().timeIntervalSince(started); DispatchQueue.main.async { done(out) } }
            guard let pandoc = PdfmdTool.pandoc() else {
                out.error = "pandoc was not found (install it, or name it in Settings > Studio)"
                return
            }
            let fm = FileManager.default
            try? fm.createDirectory(at: cacheFolder, withIntermediateDirectories: true)
            var head = "<style>\n\(builtInStyle)\n</style>\n"
            if let base = source?.deletingLastPathComponent() {
                head = "<base href=\"\(base.absoluteString.hasSuffix("/") ? base.absoluteString : base.absoluteString + "/")\">\n" + head
            }
            let css = Settings.string("htmlPreviewCSS").trimmingCharacters(in: .whitespacesAndNewlines)
            if !css.isEmpty, let extra = try? String(contentsOfFile: (css as NSString).expandingTildeInPath, encoding: .utf8) {
                head += "<style>\n\(extra)\n</style>\n"
            }
            let headFile = cacheFolder.appendingPathComponent("\(key).head.html")
            let htmlFile = cacheFolder.appendingPathComponent("\(key).html")
            do { try head.write(to: headFile, atomically: true, encoding: .utf8) } catch { out.error = "cannot write \(headFile.path)"; return }

            let p = Process()
            p.executableURL = URL(fileURLWithPath: pandoc)
            p.arguments = ["-f", "markdown", "-t", "html5", "-s", mathFlag(pandoc), "--wrap=none", "--metadata", "pagetitle=\(name)",
                           "-H", headFile.path] + shellWords(Settings.string("htmlPreviewArguments"))
            if let folder = source?.deletingLastPathComponent() { p.currentDirectoryURL = folder }
            let inPipe = Pipe(), outPipe = Pipe(), errPipe = Pipe()
            p.standardInput = inPipe
            p.standardOutput = outPipe
            p.standardError = errPipe
            do { try p.run() } catch { out.error = "cannot run pandoc: \(error.localizedDescription)"; return }
            let group = DispatchGroup()
            var html = Data(), err = Data()
            group.enter(); DispatchQueue.global().async { html = outPipe.fileHandleForReading.readDataToEndOfFile(); group.leave() }
            group.enter(); DispatchQueue.global().async { err = errPipe.fileHandleForReading.readDataToEndOfFile(); group.leave() }
            DispatchQueue.global().async { inPipe.fileHandleForWriting.write(Data(text.utf8)); try? inPipe.fileHandleForWriting.close() }
            let limit = Settings.number("studioRenderTimeout")
            var timedOut = false
            if limit > 0 {
                DispatchQueue.global().asyncAfter(deadline: .now() + limit) { if p.isRunning { timedOut = true; p.terminate() } }
            }
            p.waitUntilExit()
            group.wait()
            if timedOut { out.error = "pandoc was stopped after \(Int(limit)) s (Settings > Studio)"; return }
            guard p.terminationStatus == 0 else {
                out.error = String(decoding: err, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
                if out.error.isEmpty { out.error = "pandoc exited with status \(p.terminationStatus)" }
                return
            }
            do { try html.write(to: htmlFile, options: .atomic); out.file = htmlFile } catch { out.error = "cannot write \(htmlFile.path)" }
            let warnings = String(decoding: err, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
            if !warnings.isEmpty { out.error = warnings }   // a warning: the page is there all the same
        }
    }
}

/// The pane beside the editor's text: a switch (HTML | PDF), a status line, and the page or the PDF below.
final class PreviewPane: NSView {
    let modes = NSSegmentedControl(labels: ["HTML", "PDF"], trackingMode: .selectOne, target: nil, action: nil)
    let status = NSTextField(labelWithString: "")
    let html = HTMLPageView(javaScript: false)
    let pdf = PDFView()
    let noPDF = NSTextField(labelWithString: "No PDF yet. ⌘R builds it.")
    private let bar = NSView()
    static let barHeight: CGFloat = 30

    override init(frame: NSRect) {
        super.init(frame: frame)
        modes.segmentStyle = .rounded
        modes.controlSize = .small
        status.font = .systemFont(ofSize: 11)
        status.textColor = .secondaryLabelColor
        status.lineBreakMode = .byTruncatingTail
        status.alignment = .right
        noPDF.textColor = .secondaryLabelColor
        noPDF.alignment = .center
        pdf.backgroundColor = Desk.color
        pdf.autoScales = true
        pdf.displayMode = .singlePageContinuous
        for v in [bar, html, pdf, noPDF] as [NSView] { addSubview(v) }
        bar.addSubview(modes)
        bar.addSubview(status)
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    override func layout() {
        super.layout()
        let h = Self.barHeight
        bar.frame = NSRect(x: 0, y: bounds.height - h, width: bounds.width, height: h)
        modes.frame = NSRect(x: 8, y: 4, width: 110, height: 22)
        status.frame = NSRect(x: 126, y: 7, width: max(0, bounds.width - 134), height: 16)
        let body = NSRect(x: 0, y: 0, width: bounds.width, height: bounds.height - h)
        html.frame = body
        pdf.frame = body
        noPDF.frame = NSRect(x: 0, y: body.midY - 10, width: body.width, height: 20)
    }

    override func draw(_ dirtyRect: NSRect) {
        NSColor.windowBackgroundColor.setFill()
        dirtyRect.fill()
    }

    func showMode(_ pdfMode: Bool, hasPDF: Bool) {
        modes.selectedSegment = pdfMode ? 1 : 0
        html.isHidden = pdfMode
        pdf.isHidden = !pdfMode || !hasPDF
        noPDF.isHidden = !pdfMode || hasPDF
    }
}

/// The studio, in its first form: the editor window with a preview pane beside the text. HTML (pandoc, fast, follows the typing after a
/// pause and the scrolling of the text) or the PDF (the last build, ⌘R). A window without the pane is the plain editor; the setting
/// `startupWindow` says which one a new window is.
final class StudioController: NSObject, NSSplitViewDelegate {
    weak var owner: EditorWindowController?
    private(set) var pane: PreviewPane?
    private var split: NSSplitView?
    private var grewBy: CGFloat = 0
    private var pdfURL: URL?
    private var renderWork: DispatchWorkItem?
    private var scrollWork: DispatchWorkItem?
    private var rendering = false
    private var again = false
    private var editedSinceRender = true
    private var observers: [NSObjectProtocol] = []
    private let untitledKey = "untitled-\(UInt32.random(in: 0...UInt32.max))"
    /// For the self-test.
    private(set) var renders = 0
    private(set) var lastOutput: HTMLRender.Output?

    var isShown: Bool { pane != nil }
    var showsPDF: Bool { Settings.int("studioPaneMode") == 1 }

    private var editorDocument: EditorDocument? { owner?.document as? EditorDocument }
    private var source: URL? { editorDocument?.fileURL }

    // MARK: showing and hiding

    func toggle() { isShown ? hide() : show(growWindow: true) }

    func show(growWindow: Bool) {
        guard !isShown, let owner, let window = owner.window, let content = owner.content else { return }
        let pane = PreviewPane(frame: NSRect(x: 0, y: 0, width: 520, height: window.contentLayoutRect.height))
        self.pane = pane
        let split = NSSplitView(frame: window.contentLayoutRect)
        split.isVertical = true
        split.dividerStyle = .thin
        split.autoresizingMask = [.width, .height]
        split.delegate = self
        let editorWidth = window.contentLayoutRect.width
        content.removeFromSuperview()
        window.contentView = split
        split.addArrangedSubview(content)
        split.addArrangedSubview(pane)
        self.split = split
        let width = Settings.number("studioPaneWidth")
        if growWindow, let screen = window.screen ?? NSScreen.main {
            var frame = window.frame
            let room = screen.visibleFrame.maxX - frame.maxX
            let grow = min(width, max(0, room))
            frame.size.width += grow
            window.setFrame(frame, display: false)
            grewBy = grow
        }
        let total = window.contentLayoutRect.width
        split.setPosition(growWindow ? max(minEditor, min(editorWidth, total - minPane)) : max(minEditor, total - CGFloat(width)), ofDividerAt: 0)
        pane.modes.target = self
        pane.modes.action = #selector(modeChanged(_:))
        pane.html.onFileLink = { url in
            NSDocumentController.shared.openDocument(withContentsOf: url, display: true) { _, _, error in
                if let error { NSApp.presentError(error) }
            }
        }
        pane.html.linkBase = source?.deletingLastPathComponent()
        if let sibling = source?.deletingPathExtension().appendingPathExtension("pdf"), FileManager.default.fileExists(atPath: sibling.path) { pdfURL = sibling }
        applyMode()
        window.makeFirstResponder(owner.parts.textView)
        watch()
    }

    func hide() {
        guard let owner, let window = owner.window, let content = owner.content, let pane else { return }
        renderWork?.cancel()
        for o in observers { NotificationCenter.default.removeObserver(o) }
        observers = []
        let width = pane.frame.width
        if width >= minPane { Settings.set("studioPaneWidth", Double(Int(width))) }
        content.removeFromSuperview()
        window.contentView = content
        var frame = window.frame
        frame.size.width = max(420, frame.size.width - grewBy)
        window.setFrame(frame, display: true)
        grewBy = 0
        self.pane = nil
        self.split = nil
        window.makeFirstResponder(owner.parts.textView)
    }

    private var minEditor: CGFloat { CGFloat(Settings.number("studioMinEditorWidth")) }
    private var minPane: CGFloat { CGFloat(Settings.number("studioMinPaneWidth")) }

    func splitView(_ splitView: NSSplitView, constrainMinCoordinate proposed: CGFloat, ofSubviewAt index: Int) -> CGFloat { max(proposed, minEditor) }
    func splitView(_ splitView: NSSplitView, constrainMaxCoordinate proposed: CGFloat, ofSubviewAt index: Int) -> CGFloat { min(proposed, splitView.bounds.width - minPane) }
    /// A resized window changes the text's width; the pane keeps its own.
    func splitView(_ splitView: NSSplitView, shouldAdjustSizeOfSubview view: NSView) -> Bool { view !== pane }

    // MARK: following the text

    private func watch() {
        guard let owner else { return }
        let center = NotificationCenter.default
        observers.append(center.addObserver(forName: NSText.didChangeNotification, object: owner.parts.textView, queue: .main) { [weak self] _ in self?.textEdited() })
        let clip = owner.parts.scroll.contentView
        clip.postsBoundsChangedNotifications = true
        observers.append(center.addObserver(forName: NSView.boundsDidChangeNotification, object: clip, queue: .main) { [weak self] _ in self?.editorScrolled() })
    }

    func textEdited() {
        editedSinceRender = true
        guard isShown, !showsPDF else { return }
        renderWork?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.render() }
        renderWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(max(0, Settings.int("studioPreviewDelayMs"))), execute: work)
    }

    /// The preview shows the same part of the text as the editor: the same fraction of the way down (the heights differ, so it is near, not
    /// exact).
    private func editorFraction() -> Double? {
        guard let scroll = owner?.parts.scroll, let doc = scroll.documentView else { return nil }
        let room = doc.frame.height - scroll.contentView.bounds.height
        guard room > 1 else { return 0 }
        return min(1, max(0, Double(scroll.contentView.bounds.origin.y / room)))
    }

    private func editorScrolled() {
        guard isShown, !showsPDF, Settings.flag("studioFollow") else { return }
        scrollWork?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self, let f = self.editorFraction() else { return }
            self.pane?.html.scroll(toFraction: f)
        }
        scrollWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(max(0, Settings.int("studioScrollDelayMs"))), execute: work)
    }

    // MARK: HTML

    func render() {
        guard let owner, !showsPDF, isShown else { return }
        if rendering { again = true; return }
        rendering = true
        again = false
        editedSinceRender = false
        let name = owner.document?.displayName ?? "preview"
        let fraction = Settings.flag("studioFollow") ? editorFraction() : nil
        HTMLRender.render(owner.currentString(), source: source, name: name, key: HTMLRender.key(for: source, fallback: untitledKey)) { [weak self] out in
            guard let self else { return }
            self.rendering = false
            self.renders += 1
            self.lastOutput = out
            if let pane = self.pane {
                let first = out.error.split(separator: "\n").first.map(String.init) ?? ""
                if let file = out.file {
                    if pane.html.url == file { pane.html.reload(fraction: fraction) }
                    else { pane.html.load(file, readAccess: URL(fileURLWithPath: "/"), fraction: fraction) }
                    pane.status.stringValue = out.error.isEmpty ? String(format: "%.2f s", out.seconds) : "warning: " + first
                } else {
                    pane.status.stringValue = "error: " + first   // the old page stays
                }
                pane.status.toolTip = out.error
            }
            if self.again { self.again = false; self.render() }
        }
    }

    // MARK: PDF

    /// A build made this PDF: the pane shows it (and switches to it).
    func showBuilt(_ url: URL) {
        pdfURL = url
        Settings.set("studioPaneMode", 1)
        applyMode()
    }

    private func loadPDF() {
        guard let pane, let url = pdfURL, FileManager.default.fileExists(atPath: url.path), let doc = PDFDocument(url: url), doc.pageCount > 0 else {
            pane?.showMode(true, hasPDF: false); return
        }
        var index = 0
        var point = CGPoint(x: 0, y: 0)
        if let old = pane.pdf.document, let dest = pane.pdf.currentDestination, let page = dest.page {
            index = min(old.index(for: page), doc.pageCount - 1)
            point = dest.point
        }
        pane.pdf.document = doc
        pane.pdf.autoScales = true
        if let page = doc.page(at: index) { pane.pdf.go(to: PDFDestination(page: page, at: point)) }
        pane.showMode(true, hasPDF: true)
        pane.status.stringValue = url.lastPathComponent
    }

    @objc func modeChanged(_ sender: NSSegmentedControl) { setMode(pdf: sender.selectedSegment == 1) }

    func setMode(pdf: Bool) {
        Settings.set("studioPaneMode", pdf ? 1 : 0)
        applyMode()
    }

    private func applyMode() {
        guard let pane else { return }
        if showsPDF {
            loadPDF()
        } else {
            pane.showMode(false, hasPDF: pdfURL != nil)
            if renders == 0 || editedSinceRender { render() }
        }
    }
}
