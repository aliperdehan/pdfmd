import Cocoa
import ServiceManagement

/// The popup's window. It takes the keys that the popup owns (command return, command R, command S, command W) before the main menu
/// sees them, so that they do not depend on the menu: the menu's own command R is the editor's Build, command S the document's Save.
final class PopPanel: NSPanel {
    var handleKey: ((NSEvent) -> Bool)?
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }   // an editor window stays the main window of the app
    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        if handleKey?(event) == true { return true }
        return super.performKeyEquivalent(with: event)
    }
    override func cancelOperation(_ sender: Any?) { PopController.shared.hide() }
}

/// The preview. A drag from it carries the result as PDF, PNG and a file, so it can be dropped into Keynote, Word, Finder…
final class PopPreviewView: NSImageView, NSDraggingSource {
    var dragItem: (() -> NSPasteboardItem?)?

    override var mouseDownCanMoveWindow: Bool { false }
    override func mouseDown(with event: NSEvent) {}
    func draggingSession(_ session: NSDraggingSession, sourceOperationMaskFor context: NSDraggingContext) -> NSDragOperation { .copy }

    override func mouseDragged(with event: NSEvent) {
        guard let item = dragItem?(), let img = image else { return }
        let di = NSDraggingItem(pasteboardWriter: item)
        di.setDraggingFrame(bounds, contents: img)
        beginDraggingSession(with: [di], event: event, source: self)
    }
}

/// The equation popup: a floating window that renders a LaTeX or Markdown snippet to a cropped vector PDF and copies it. It was the
/// separate app eqpop. The window is built on first use; the menu-bar icon and the global shortcut exist only while the setting
/// `popMenuBar` is on. Every choice it keeps is a setting (`pop...`), so `colophon settings` reaches all of them.
final class PopController: NSObject, NSTextViewDelegate {
    static let shared = PopController()

    // the window
    var panel: PopPanel!
    var input: NSTextView!
    let modePopup = NSPopUpButton(frame: .zero, pullsDown: false)
    let enginePopup = NSPopUpButton(frame: .zero, pullsDown: false)
    let pdfmdPopup = NSPopUpButton(frame: .zero, pullsDown: false)
    let status = NSTextField(wrappingLabelWithString: "")
    let preview = PopPreviewView()
    let errors = PopErrorList()
    let logWindow = PopLogWindow()
    var preambleView: NSTextView!
    var preambleScroll: NSScrollView!
    var paneBox: NSView!
    var paneSeg: NSSegmentedControl!       // 0 = LaTeX preamble, 1 = pdfmd metadata
    var inputEditing: PopTeXEditing!
    var preambleEditing: PopTeXEditing!
    var inputScroll: NSScrollView!
    var liveBox: NSButton!
    var logButton: NSButton!
    var preambleHeight: NSLayoutConstraint!
    var preambleGap: NSLayoutConstraint!
    var chain: [NSLayoutConstraint] = []   // the vertical order of the rows; changes with the preview position
    var content: NSView!
    var rows: [NSView] = []                // preview, status, the pane (and the editor under it), the option row, the buttons
    static var preamblePaneHeight: CGFloat { CGFloat(Settings.number("popPaneHeight")) }
    var built = false
    var offscreen = false                  // tests and screenshots: the window is never shown, nothing is saved

    // what it does
    let renderer = PopRenderer()
    var lastPDF: Data?
    var lastKey: String?                   // what lastPDF was rendered from; nil after a failed render
    var lastLog = ""
    var wantCopy = false
    var debounce: Timer?
    var pasteboard: NSPasteboard = .general   // tests copy to a private one
    var previousApp: NSRunningApplication?
    var returnWindow: NSWindow?

    // the menu bar
    var statusItem: NSStatusItem?
    let hotkey = PopHotKey()
    var hotkeyNote: String?                // why the shortcut does not work, shown in the icon's menu (never as an alert at launch)
    var loginNote: String?

    var live: Bool { Settings.flag("popLive") }
    var hideAfterCopy: Bool { Settings.flag("popHideAfterCopy") }
    var previewAbove: Bool { Settings.flag("popPreviewAbove") }
    var lineNumbers: Bool { Settings.flag("popLineNumbers") }
    var preambleShown: Bool { Settings.flag("popPreambleShown") }

    /// A choice made in the window is stored without announcing it (the window already shows it).
    func keep(_ key: String, _ value: Any) { if !offscreen { Settings.store.set(value, forKey: key) } }

    static func plainCode(_ t: NSTextView) {
        t.font = editorFont()
        t.isAutomaticQuoteSubstitutionEnabled = false
        t.isAutomaticDashSubstitutionEnabled = false
        t.isAutomaticTextReplacementEnabled = false
        t.isAutomaticSpellingCorrectionEnabled = false
        t.isContinuousSpellCheckingEnabled = false
        t.isAutomaticLinkDetectionEnabled = false
        t.isRichText = false
        t.allowsUndo = true
        t.textContainerInset = NSSize(width: 4, height: 6)
    }

    // MARK: the window

    func ensureBuilt() {
        guard !built else { return }
        built = true
        _ = PopStore.preamble()   // creates the preamble file on first use only
        buildPanel()
    }

    static let sample = "\\ce{CH4 + 2O2 -> CO2 + 2H2O}\n\\qquad \\Delta H^\\circ = \\SI{-890}{\\kilo\\joule\\per\\mole}"

    func buildPanel() {
        let scroll = NSTextView.scrollableTextView()
        input = scroll.documentView as? NSTextView
        PopController.plainCode(input)
        input.delegate = self
        input.string = Settings.store.string(forKey: "popSource") ?? "\\ce{2H2 + O2 -> 2H2O}"
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder
        scroll.heightAnchor.constraint(equalToConstant: CGFloat(Settings.number("popEditorHeight"))).isActive = true
        inputEditing = PopTeXEditing(input)
        inputScroll = scroll
        scroll.verticalRulerView = PopLineNumbers(scroll, input)
        scroll.hasVerticalRuler = true

        preambleScroll = NSTextView.scrollableTextView()
        preambleView = preambleScroll.documentView as? NSTextView
        PopController.plainCode(preambleView)
        preambleView.delegate = self
        preambleView.string = PopStore.preamble()
        preambleScroll.hasVerticalScroller = true
        preambleScroll.borderType = .bezelBorder
        preambleEditing = PopTeXEditing(preambleView)
        preambleScroll.verticalRulerView = PopLineNumbers(preambleScroll, preambleView)
        preambleScroll.hasVerticalRuler = true
        paneSeg = NSSegmentedControl(labels: ["Preamble", "pdfmd metadata"], trackingMode: .selectOne, target: self, action: #selector(paneChanged))
        paneSeg.controlSize = .small
        paneSeg.selectedSegment = 0
        paneBox = NSView()
        paneBox.isHidden = true   // showSettings opens it when the setting says so
        for v in [paneSeg!, preambleScroll!] { v.translatesAutoresizingMaskIntoConstraints = false; paneBox.addSubview(v) }
        NSLayoutConstraint.activate([
            paneSeg.topAnchor.constraint(equalTo: paneBox.topAnchor),
            paneSeg.leadingAnchor.constraint(equalTo: paneBox.leadingAnchor),
            preambleScroll.topAnchor.constraint(equalTo: paneSeg.bottomAnchor, constant: 4),
            preambleScroll.leadingAnchor.constraint(equalTo: paneBox.leadingAnchor),
            preambleScroll.trailingAnchor.constraint(equalTo: paneBox.trailingAnchor),
            preambleScroll.bottomAnchor.constraint(equalTo: paneBox.bottomAnchor),
        ])

        for m in PopMode.allCases { modePopup.addItem(withTitle: m.title); modePopup.lastItem?.representedObject = m.rawValue }
        modePopup.target = self; modePopup.action = #selector(optionsChanged)
        enginePopup.autoenablesItems = false
        for e in PopEngine.allCases {
            enginePopup.addItem(withTitle: e.rawValue)
            enginePopup.lastItem?.isEnabled = e == .pdfmd ? true : PopToolchain.find(e.rawValue) != nil   // pdfmd is looked for when it is used
        }
        enginePopup.target = self; enginePopup.action = #selector(optionsChanged)
        pdfmdPopup.addItems(withTitles: popPdfmdEngines)
        pdfmdPopup.toolTip = "The PDF engine pdfmd uses (its -e). auto: pdfmd's own choice."
        pdfmdPopup.target = self; pdfmdPopup.action = #selector(optionsChanged)

        status.font = .systemFont(ofSize: 11)
        status.textColor = .secondaryLabelColor
        status.maximumNumberOfLines = 4
        status.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

        preview.imageScaling = .scaleProportionallyUpOrDown
        preview.imageAlignment = .alignCenter
        preview.isEditable = false
        preview.wantsLayer = true
        preview.layer?.backgroundColor = NSColor.white.cgColor   // black text stays readable in dark mode
        preview.layer?.cornerRadius = 6
        preview.layer?.borderWidth = 1
        preview.layer?.borderColor = NSColor(white: 0.5, alpha: 0.35).cgColor   // keeps the white sheet visible on a light window
        preview.setContentHuggingPriority(.defaultLow, for: .vertical)
        preview.heightAnchor.constraint(greaterThanOrEqualToConstant: CGFloat(Settings.number("popPreviewMinHeight"))).isActive = true
        preview.dragItem = { [weak self] in self?.pasteboardItem() }
        errors.onJump = { [weak self] line in self?.jump(toLine: line) }
        errors.scroll.isHidden = true

        liveBox = NSButton(checkboxWithTitle: "Live", target: self, action: #selector(toggleLive))
        liveBox.toolTip = "Render while typing. Off: render with ⌘R, or with ⌘↩ (which also copies)."
        let edit = NSButton(title: "Preamble", target: self, action: #selector(togglePreamble))
        let save = NSButton(title: "Save…", target: self, action: #selector(saveAs))
        logButton = NSButton(title: "Log", target: self, action: #selector(showLog))
        let copy = NSButton(title: "Copy  ⌘↩", target: self, action: #selector(copyRendered))
        copy.bezelStyle = .rounded
        // plain constraints, and every row but the preview has a fixed height: the preview takes all the extra room
        content = NSView()
        let m: CGFloat = 12
        for v in [paneBox!, scroll, modePopup, enginePopup, pdfmdPopup, liveBox!, preview, errors.scroll, status, edit, save, logButton!, copy] {
            v.translatesAutoresizingMaskIntoConstraints = false
            content.addSubview(v)
        }
        NSLayoutConstraint.activate([
            paneBox.leadingAnchor.constraint(equalTo: scroll.leadingAnchor),
            paneBox.trailingAnchor.constraint(equalTo: scroll.trailingAnchor),
            scroll.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: m),
            scroll.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -m),
            modePopup.leadingAnchor.constraint(equalTo: scroll.leadingAnchor),
            enginePopup.leadingAnchor.constraint(equalTo: modePopup.trailingAnchor, constant: 8),
            enginePopup.centerYAnchor.constraint(equalTo: modePopup.centerYAnchor),
            pdfmdPopup.leadingAnchor.constraint(equalTo: enginePopup.trailingAnchor, constant: 8),
            pdfmdPopup.centerYAnchor.constraint(equalTo: modePopup.centerYAnchor),
            liveBox.trailingAnchor.constraint(equalTo: scroll.trailingAnchor),
            liveBox.centerYAnchor.constraint(equalTo: modePopup.centerYAnchor),
            preview.leadingAnchor.constraint(equalTo: scroll.leadingAnchor),
            preview.trailingAnchor.constraint(equalTo: scroll.trailingAnchor),
            errors.scroll.topAnchor.constraint(equalTo: preview.topAnchor),
            errors.scroll.bottomAnchor.constraint(equalTo: preview.bottomAnchor),
            errors.scroll.leadingAnchor.constraint(equalTo: preview.leadingAnchor),
            errors.scroll.trailingAnchor.constraint(equalTo: preview.trailingAnchor),
            status.leadingAnchor.constraint(equalTo: scroll.leadingAnchor),
            status.trailingAnchor.constraint(equalTo: scroll.trailingAnchor),
            edit.leadingAnchor.constraint(equalTo: scroll.leadingAnchor),
            save.leadingAnchor.constraint(equalTo: edit.trailingAnchor, constant: 8),
            save.centerYAnchor.constraint(equalTo: edit.centerYAnchor),
            logButton.leadingAnchor.constraint(equalTo: save.trailingAnchor, constant: 8),
            logButton.centerYAnchor.constraint(equalTo: edit.centerYAnchor),
            copy.trailingAnchor.constraint(equalTo: scroll.trailingAnchor),
            copy.centerYAnchor.constraint(equalTo: edit.centerYAnchor),
        ])
        preambleHeight = paneBox.heightAnchor.constraint(equalToConstant: 0)
        preambleGap = scroll.topAnchor.constraint(equalTo: paneBox.bottomAnchor, constant: 0)
        NSLayoutConstraint.activate([preambleHeight, preambleGap])
        rows = [preview, status, paneBox, modePopup, edit]   // the rows, see applyLayout

        panel = PopPanel(contentRect: NSRect(x: 0, y: 0, width: Settings.number("popWidth"), height: Settings.number("popHeight")), styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        panel.title = "Equation popup"
        panel.isReleasedWhenClosed = false
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.contentView = content
        panel.handleKey = { [weak self] e in self?.handleKey(e) ?? false }
        showSettings()
        if offscreen { panel.center(); return }   // never touch the saved frame
        panel.setFrameAutosaveName("popPanel")
        if !panel.setFrameUsingName("popPanel") { panel.center() }
    }

    /// Puts what the settings say into the controls: the layout, the choices, the rulers and the pane. Called when the window is built and
    /// whenever a setting changes (`colophon settings set popLive off` takes effect in the open window).
    func showSettings() {
        guard built else { return }
        liveBox.state = live ? .on : .off
        let mode = PopMode(rawValue: Settings.string("popMode")) ?? .display
        modePopup.selectItem(at: PopMode.allCases.firstIndex(of: mode) ?? 0)
        let engine = PopEngine(rawValue: Settings.string("popEngine")) ?? .pdflatex
        enginePopup.selectItem(withTitle: engine.rawValue)
        pdfmdPopup.selectItem(withTitle: Settings.string("popPdfmdEngine"))
        applyEngineChoice()
        applyLayout()
        inputScroll.rulersVisible = lineNumbers
        preambleScroll.rulersVisible = lineNumbers
        setPreamblePane(shown: preambleShown)
        content.needsLayout = true
    }

    /// The rows run top to bottom in one chain: the preview and its status line, the pane with the editor, the options, the
    /// buttons. The preview goes first or comes right after the editor and the options, as the setting says.
    func applyLayout() {
        NSLayoutConstraint.deactivate(chain)
        let m: CGFloat = 12
        let (preview, status, pane, options, buttons) = (rows[0], rows[1], rows[2], rows[3], rows[4])
        let editor = inputScroll!
        // each row as (its top view, its bottom view)
        let order: [(NSView, NSView)] = previewAbove
            ? [(preview, preview), (status, status), (pane, editor), (options, options), (buttons, buttons)]
            : [(pane, editor), (options, options), (preview, preview), (status, status), (buttons, buttons)]
        var c = [order[0].0.topAnchor.constraint(equalTo: content.topAnchor, constant: m),
                 order[order.count - 1].1.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -m)]
        for i in 1..<order.count { c.append(order[i].0.topAnchor.constraint(equalTo: order[i - 1].1.bottomAnchor, constant: 8)) }
        chain = c
        NSLayoutConstraint.activate(chain)
    }

    /// Shows or hides the preamble pane; the window grows and shrinks by the pane's height, so the rest keeps its size.
    func setPreamblePane(shown: Bool) {
        let isShown = !paneBox.isHidden
        guard shown != isShown else { return }
        if shown { loadPane() }   // an edit made in another editor is picked up
        let delta = PopController.preamblePaneHeight + 8
        paneBox.isHidden = !shown
        preambleHeight.constant = shown ? PopController.preamblePaneHeight : 0
        preambleGap.constant = shown ? 8 : 0
        if panel != nil {
            var f = panel.frame
            f.size.height += shown ? delta : -delta
            f.origin.y -= shown ? delta : -delta   // the top edge stays where it is
            panel.setFrame(f, display: true, animate: false)
        }
        if !shown, panel != nil, panel.isKeyWindow { panel.makeFirstResponder(input) }
    }

    // MARK: keys

    /// command return copies, command R renders, command S saves, command W hides: the popup's own, whatever the menu says.
    func handleKey(_ e: NSEvent) -> Bool {
        guard e.modifierFlags.intersection(.deviceIndependentFlagsMask) == .command else { return false }
        switch e.charactersIgnoringModifiers {
        case "\r", "\u{3}": copyRendered(); return true
        case "r": renderNowAction(); return true
        case "s": saveAs(); return true
        case "w": hide(); return true
        default: return false
        }
    }

    func textViewDidChangeSelection(_ n: Notification) {
        guard let tv = n.object as? NSTextView else { return }
        (tv === preambleView ? preambleEditing : inputEditing)?.updateBrackets()
    }

    func textView(_ t: NSTextView, doCommandBy sel: Selector) -> Bool {
        if sel == #selector(NSResponder.cancelOperation(_:)) { hide(); return true }
        return false
    }

    // MARK: show and hide

    func toggle() { built && panel.isVisible && NSApp.isActive ? hide() : show() }

    /// The menu item: opens the popup, or closes it when it is the open one.
    @objc func toggleWindow() { toggle() }

    @objc func show() {
        ensureBuilt()
        if !panel.isVisible {   // where the focus goes back to when the popup closes
            if let front = NSWorkspace.shared.frontmostApplication, front != NSRunningApplication.current {
                previousApp = front; returnWindow = nil
            } else {
                previousApp = nil; returnWindow = NSApp.keyWindow
            }
        }
        NSApp.activate(ignoringOtherApps: true)
        panel.makeKeyAndOrderFront(nil)
        panel.makeFirstResponder(input)
        input.setSelectedRange(NSRange(location: input.string.utf16.count, length: 0))   // keep the text: a stray key must not wipe it
        if lastPDF == nil && !selectedEngine.isSlow { schedule(after: 0) }
    }

    /// Closes the popup and gives the focus back to what had it. (Not `NSApp.hide`: that would hide every editor window of Colophon.)
    @objc func hide() {
        guard built else { return }
        panel.orderOut(nil)
        if let prev = previousApp, !prev.isTerminated {
            prev.activate(options: [])
        } else if let w = returnWindow, w.isVisible {
            w.makeKeyAndOrderFront(nil)
        }
        previousApp = nil; returnWindow = nil
    }

    // MARK: rendering

    func textDidChange(_ n: Notification) {
        if (n.object as? NSTextView) === preambleView {
            let file = paneSeg.selectedSegment == 1 ? PopStore.metadataURL : PopStore.preambleURL
            if !offscreen { try? preambleView.string.write(to: file, atomically: true, encoding: .utf8) }   // the file is the source of truth
            changed(after: Settings.number("popPreambleDelayMs") / 1000)
        } else {
            keep("popSource", input.string)
            changed(after: Settings.number("popRenderDelayMs") / 1000)
        }
    }

    @objc func optionsChanged() {
        keep("popMode", selectedMode.rawValue)
        keep("popEngine", selectedEngine.rawValue)
        keep("popPdfmdEngine", pdfmdPopup.titleOfSelectedItem ?? "auto")
        applyEngineChoice()
        changed(after: 0)
    }

    /// What depends on the engine: pdfmd takes Markdown (no mode) and has a PDF engine of its own and a metadata tab.
    func applyEngineChoice() {
        let md = selectedEngine == .pdfmd
        modePopup.isEnabled = !md
        pdfmdPopup.isHidden = !md
        paneSeg?.setEnabled(md, forSegment: 1)
        if !md, paneSeg?.selectedSegment == 1 { paneSeg.selectedSegment = 0; loadPane() }
    }

    @objc func paneChanged() { loadPane() }

    /// Shows the file of the selected tab (preamble or pdfmd metadata) in the pane.
    func loadPane() {
        let meta = paneSeg.selectedSegment == 1
        preambleEditing.yaml = meta
        preambleView.string = meta ? PopStore.metadata() : PopStore.preamble()
    }

    func makeRequest(_ src: String) -> PopRequest {
        PopRequest(source: src, mode: selectedMode, engine: selectedEngine, preamble: PopStore.preamble(),
                   pdfmdEngine: pdfmdPopup.titleOfSelectedItem ?? "auto", metadata: PopStore.metadata())
    }

    func jump(toLine line: Int) {
        let s = input.string as NSString
        var start = 0, n = 1
        while n < line, start < s.length {
            let r = s.range(of: "\n", range: NSRange(location: start, length: s.length - start))
            if r.location == NSNotFound { break }
            start = NSMaxRange(r); n += 1
        }
        let range = s.lineRange(for: NSRange(location: min(start, s.length), length: 0))
        panel.makeFirstResponder(input)
        input.setSelectedRange(range)
        input.scrollRangeToVisible(range)
    }

    @objc func showLog() { logWindow.show(lastLog) }

    var selectedMode: PopMode { PopMode(rawValue: modePopup.selectedItem?.representedObject as? String ?? "") ?? .display }
    var selectedEngine: PopEngine { PopEngine(rawValue: enginePopup.titleOfSelectedItem ?? "") ?? .pdflatex }

    /// The input changed: render after a pause when live, else just say that the preview is out of date.
    func changed(after delay: TimeInterval) {
        if live && !selectedEngine.isSlow { schedule(after: delay); return }
        debounce?.invalidate()
        renderer.cancel()
        if selectedEngine.isSlow { setStatus("pdfmd takes a few seconds: ⌘R renders", error: false) }
        else if lastPDF != nil { setStatus("edited: ⌘R renders", error: false) }
    }

    @objc func renderNowAction() { schedule(after: 0) }

    @objc func toggleLive() { Settings.set("popLive", live ? 0 : 1) }   // announces itself: showSettings and the menu follow

    func schedule(after delay: TimeInterval) {
        debounce?.invalidate()
        debounce = Timer.scheduledTimer(withTimeInterval: delay, repeats: false) { [weak self] _ in self?.renderNow() }
    }

    func renderNow() {
        let src = input.string.trimmingCharacters(in: .whitespacesAndNewlines)
        if src.isEmpty {
            renderer.cancel(); lastPDF = nil; preview.image = nil; setStatus("", error: false)
            errors.scroll.isHidden = true; preview.isHidden = false
            return
        }
        setStatus("rendering…", error: false)
        let started = Date()
        let req = makeRequest(src)
        let key = PopController.key(req)
        renderer.render(req) { [weak self] result in
            guard let self = self else { return }
            switch result {
            case .success(let r):
                let pdf = r.pdf
                self.lastLog = r.log
                self.errors.scroll.isHidden = true
                self.preview.isHidden = false
                self.lastPDF = pdf
                self.lastKey = key
                self.preview.image = NSImage(data: pdf)
                let size = PopPDFTools.pointSize(pdf).map { String(format: "%.0f × %.0f pt", $0.width, $0.height) } ?? ""
                let more = r.pages > 1 ? " · page 1 of \(r.pages)" : ""
                self.setStatus(String(format: "%@ · %.2f s", size, Date().timeIntervalSince(started)) + more, error: false)
                if self.wantCopy { self.wantCopy = false; self.finishCopy(pdf) }
            case .failure(.cancelled):
                break
            case .failure(.noEngine(let name)):
                self.failed()
                let how = name == "pdfmd" ? "pipx install pdfmd-cli" : "install MacTeX or BasicTeX"
                self.errors.scroll.isHidden = true
                self.preview.isHidden = false
                self.setStatus("\(name) not found (\(how)), or pick another engine.", error: true)
            case .failure(.failed(let f)):
                self.failed()
                self.lastLog = f.log
                self.errors.issues = f.issues
                self.errors.scroll.isHidden = false
                self.preview.isHidden = true
                let n = f.issues.count
                self.setStatus(f.issues.contains { $0.line != nil } ? "\(n) error\(n == 1 ? "" : "s"): double-click a line to jump to it" : "\(n) message\(n == 1 ? "" : "s")", error: true)
            }
        }
    }

    /// A failed render: what is on screen is no longer the current text, and a pending copy must not take it instead.
    func failed() {
        lastKey = nil
        if wantCopy { wantCopy = false; NSSound.beep() }
    }

    /// What a result was made from. pdfmd reads neither the mode nor the popup's preamble, so they are not part of its key.
    static func key(_ r: PopRequest) -> String {
        r.engine == .pdfmd ? "pdfmd|\(r.pdfmdEngine)|\(r.preamble)|\(r.metadata)|\(r.source)"
                           : "\(r.mode.rawValue)|\(r.engine.rawValue)|\(r.preamble)|\(r.source)"
    }

    func setStatus(_ s: String, error: Bool) {
        status.stringValue = s
        status.textColor = error ? .systemRed : .secondaryLabelColor
        status.toolTip = error ? s : nil
    }

    // MARK: copy, drag, save

    @objc func copyRendered() {
        // copy only a result made from exactly what is in the window now; otherwise render again and copy that
        let src = input.string.trimmingCharacters(in: .whitespacesAndNewlines)
        let now = PopController.key(makeRequest(src))
        if let pdf = lastPDF, lastKey == now { finishCopy(pdf) }
        else { wantCopy = true; schedule(after: 0) }
    }

    func finishCopy(_ pdf: Data) {
        PopPDFTools.copyToClipboard(pdf, to: pasteboard)
        setStatus("copied (PDF + PNG)", error: false)
        if hideAfterCopy, !offscreen { hide() }
    }

    func pasteboardItem() -> NSPasteboardItem? {
        guard let pdf = lastPDF else { return nil }
        let file = PopStore.cacheDir.appendingPathComponent("equation.pdf")
        guard (try? pdf.write(to: file)) != nil else { return nil }
        let pbi = NSPasteboardItem()
        pbi.setData(pdf, forType: .pdf)
        if let png = PopPDFTools.png(from: pdf) { pbi.setData(png, forType: .png) }
        pbi.setString(file.absoluteString, forType: .fileURL)
        return pbi
    }

    @objc func togglePreamble() { Settings.set("popPreambleShown", preambleShown ? 0 : 1) }

    @objc func editPreamble() {
        show()
        if !preambleShown { Settings.set("popPreambleShown", 1) }
        panel.makeFirstResponder(preambleView)
    }

    @objc func revealPreamble() { _ = PopStore.preamble(); NSWorkspace.shared.activateFileViewerSelecting([PopStore.preambleURL]) }

    @objc func saveAs() {
        guard let pdf = lastPDF else { NSSound.beep(); return }
        let formats = ["pdf", "png", "svg"]
        let chooser = NSPopUpButton(frame: NSRect(x: 0, y: 0, width: 120, height: 26), pullsDown: false)
        chooser.addItems(withTitles: ["PDF", "PNG", "SVG"])
        let sp = NSSavePanel()
        sp.nameFieldStringValue = "equation.pdf"
        sp.accessoryView = chooser
        sp.isExtensionHidden = false
        let change = PopChooserAction { [weak sp, weak chooser] in
            guard let sp = sp, let c = chooser else { return }
            sp.nameFieldStringValue = ((sp.nameFieldStringValue as NSString).deletingPathExtension as NSString).appendingPathExtension(formats[c.indexOfSelectedItem]) ?? ""
        }
        chooser.target = change
        chooser.action = #selector(PopChooserAction.go)
        panel.level = .normal   // the save dialog must not hide behind the floating panel
        NSApp.activate(ignoringOtherApps: true)
        let answer = sp.runModal()
        panel.level = .floating
        guard answer == .OK, let url = sp.url else { return }
        let data: Data?
        switch url.pathExtension.lowercased() {
        case "png": data = PopPDFTools.png(from: pdf)
        case "svg":
            data = PopPDFTools.svg(from: pdf)
            if data == nil { warn("SVG needs pdftocairo (brew install poppler) or mutool (brew install mupdf-tools).") }
        default: data = pdf
        }
        if let d = data { do { try d.write(to: url); setStatus("saved \(url.lastPathComponent)", error: false) } catch { warn(error.localizedDescription) } }
    }

    func warn(_ text: String) {
        let a = NSAlert()
        a.messageText = "Equation popup"
        a.informativeText = text
        NSApp.activate(ignoringOtherApps: true)
        a.runModal()
    }

    // MARK: the menu bar, the shortcut, the login item

    /// Called at launch and whenever a setting changes: the icon and the shortcut exist while `popMenuBar` is on; the open window follows
    /// the other settings.
    func settingsChanged() {
        if !offscreen {   // a test must neither put an icon in the menu bar nor touch the login items
            applyMenuBar()
            applyLogin()
        }
        showSettings()
        guard built, panel.isVisible else { return }
        let src = input.string.trimmingCharacters(in: .whitespacesAndNewlines)
        if !src.isEmpty, lastKey != PopController.key(makeRequest(src)) { changed(after: 0) }   // the engine or mode was changed from outside
    }

    func applyMenuBar() {
        let want = Settings.flag("popMenuBar")
        if want {
            if statusItem == nil {
                let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
                item.button?.image = PopController.menuBarGlyph()
                statusItem = item
            }
            PopHotKey.action = { PopController.shared.toggle() }
            hotkeyNote = nil
            if let s = PopShortcut.current() {
                if !hotkey.register(s) {
                    hotkeyNote = "\(s.label) could not be registered (macOS refused it). Choose another: colophon settings set popHotkey ⌃⌥T"
                }
            } else {
                hotkey.unregister()
            }
            rebuildMenu()
        } else {
            hotkey.unregister()
            hotkeyNote = nil
            if let item = statusItem { NSStatusBar.system.removeStatusItem(item); statusItem = nil }
        }
    }

    func applyLogin() {
        guard Settings.store.object(forKey: "popLaunchAtLogin") != nil else { return }   // never undo a login item that the user made in System Settings
        let want = Settings.flag("popLaunchAtLogin")
        let has = SMAppService.mainApp.status == .enabled
        guard want != has else { loginNote = nil; return }
        do {
            if want { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
            loginNote = nil
        } catch { loginNote = "Start at login: \(error.localizedDescription)" }
        rebuildMenu()
    }

    /// "f(x)" set in STIX (shipped with macOS, SIL OFL) as a template image, so the menu bar tints it. Falls back to the system symbol.
    static func menuBarGlyph() -> NSImage? {
        guard let it = NSFont(name: "STIXGeneral-Italic", size: 15), let up = NSFont(name: "STIXGeneral-Regular", size: 15) else {
            return NSImage(systemSymbolName: "function", accessibilityDescription: "Equation popup")
        }
        let s = NSMutableAttributedString()
        for (t, f) in [("f", it), ("(", up), ("x", it), (")", up)] {
            s.append(NSAttributedString(string: t, attributes: [.font: f, .foregroundColor: NSColor.black]))
        }
        let line = CTLineCreateWithAttributedString(s)
        let ink = CTLineGetBoundsWithOptions(line, .useGlyphPathBounds)   // the outlines: the italic f hangs left of its origin
        let img = NSImage(size: NSSize(width: ceil(ink.width) + 4, height: 18), flipped: false) { r in
            guard let ctx = NSGraphicsContext.current?.cgContext else { return false }
            ctx.textPosition = CGPoint(x: 2 - ink.minX, y: r.height / 2 - ink.midY)
            CTLineDraw(line, ctx)
            return true
        }
        img.isTemplate = true
        img.accessibilityDescription = "Equation popup"
        return img
    }

    /// The menu of the icon. Its switches are the settings: choosing one writes the setting, and everything follows from that.
    func makeMenu() -> NSMenu {
        let m = NSMenu()
        let label = PopShortcut.current()?.label
        m.addItem(withTitle: "Show Equation Popup" + (label.map { "  (\($0))" } ?? ""), action: #selector(show), keyEquivalent: "").target = self
        for note in [hotkeyNote, loginNote].compactMap({ $0 }) {
            let n = NSMenuItem(title: note, action: nil, keyEquivalent: "")
            n.isEnabled = false
            m.addItem(n)
        }
        m.addItem(withTitle: "Edit preamble", action: #selector(editPreamble), keyEquivalent: "").target = self
        m.addItem(withTitle: "Show preamble file in Finder", action: #selector(revealPreamble), keyEquivalent: "").target = self
        m.addItem(.separator())
        for (title, key) in [("Live preview", "popLive"), ("Hide after copying", "popHideAfterCopy"), ("Preview above the editor", "popPreviewAbove"),
                             ("Line numbers", "popLineNumbers"), ("Start at login", "popLaunchAtLogin")] {
            let item = m.addItem(withTitle: title, action: #selector(toggleSetting(_:)), keyEquivalent: "")
            item.target = self
            item.representedObject = key
            item.state = Settings.flag(key) ? .on : .off
        }
        m.addItem(withTitle: "Change shortcut…", action: #selector(changeShortcut), keyEquivalent: "").target = self
        m.addItem(.separator())
        m.addItem(withTitle: "New Colophon Window", action: #selector(newWindow), keyEquivalent: "").target = self
        m.addItem(withTitle: "Settings…", action: #selector(openSettings), keyEquivalent: "").target = self
        m.addItem(.separator())
        m.addItem(withTitle: "Quit Colophon", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "")
        return m
    }

    func rebuildMenu() { statusItem?.menu = makeMenu() }

    @objc func toggleSetting(_ sender: NSMenuItem) {
        guard let key = sender.representedObject as? String else { return }
        Settings.set(key, Settings.flag(key) ? 0 : 1)
        rebuildMenu()
    }

    @objc func newWindow() { NSDocumentController.shared.newDocument(nil); NSApp.activate(ignoringOtherApps: true) }
    @objc func openSettings() { PreferencesController.shared.show() }

    @objc func changeShortcut() {
        let catcher = PopShortcutCatcher(frame: NSRect(x: 0, y: 0, width: 260, height: 40))
        catcher.field.stringValue = PopShortcut.current()?.label ?? "none"
        let a = NSAlert()
        a.messageText = "Press the new shortcut"
        a.informativeText = "Use Control, Option or Command with a key."
        a.accessoryView = catcher
        a.addButton(withTitle: "Save")
        a.addButton(withTitle: "Cancel")
        NSApp.activate(ignoringOtherApps: true)
        a.window.initialFirstResponder = catcher
        DispatchQueue.main.async { a.window.makeFirstResponder(catcher) }
        guard a.runModal() == .alertFirstButtonReturn, let s = catcher.captured else { return }
        let old = PopShortcut.current()
        if hotkey.register(s) { Settings.set("popHotkey", s.label) }
        else {
            if let old { _ = hotkey.register(old) }
            warn("\(s.label) is taken by another app.")
        }
    }

    // MARK: off-screen pictures (tests and the README)

    /// Renders the text of the window and returns the window drawn to a bitmap, with rounded corners and a shadow, without ever putting it on
    /// the screen: nothing appears, and no key can land in it.
    func snapshot(timeout: Double = 60) -> NSBitmapImageRep? {
        ensureBuilt()
        renderNow()
        let end = Date().addingTimeInterval(timeout)
        while Date() < end {
            RunLoop.current.run(until: Date().addingTimeInterval(0.1))
            if !status.stringValue.isEmpty && status.stringValue != "rendering…" { break }
        }
        panel.contentView?.layoutSubtreeIfNeeded()
        guard let frame = panel.contentView?.superview, let rep = frame.bitmapImageRepForCachingDisplay(in: frame.bounds) else { return nil }
        frame.cacheDisplay(in: frame.bounds, to: rep)
        return PopController.withWindowEdges(rep)
    }

    /// The captured frame has square corners and no shadow: round it and give it a shadow on a transparent margin.
    static func withWindowEdges(_ rep: NSBitmapImageRep) -> NSBitmapImageRep {
        let pad = 60, radius: CGFloat = 26
        let w = rep.pixelsWide + 2 * pad, h = rep.pixelsHigh + 2 * pad
        let out = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h, bitsPerSample: 8, samplesPerPixel: 4,
                                   hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: out)
        let box = NSRect(x: pad, y: pad, width: rep.pixelsWide, height: rep.pixelsHigh)
        let shape = NSBezierPath(roundedRect: box, xRadius: radius, yRadius: radius)
        NSGraphicsContext.saveGraphicsState()
        let sh = NSShadow()
        sh.shadowOffset = NSSize(width: 0, height: -14); sh.shadowBlurRadius = 36
        sh.shadowColor = NSColor.black.withAlphaComponent(0.45)
        sh.set(); NSColor.black.setFill(); shape.fill()
        NSGraphicsContext.restoreGraphicsState()
        shape.addClip()
        let img = NSImage(size: NSSize(width: rep.pixelsWide, height: rep.pixelsHigh)); img.addRepresentation(rep)
        img.draw(in: box)
        NSColor(white: 1, alpha: 0.12).setStroke(); shape.lineWidth = 2; shape.stroke()   // the hairline macOS draws
        NSGraphicsContext.restoreGraphicsState()
        out.size = NSSize(width: w / 2, height: h / 2)   // 2x
        return out
    }
}

/// Lets a closure be the target of a control.
final class PopChooserAction: NSObject {
    let body: () -> Void
    init(_ body: @escaping () -> Void) { self.body = body }
    @objc func go() { body() }
}

/// The failed render's errors in place of the preview: line, message, and the text TeX had just read.
final class PopErrorList: NSObject, NSTableViewDataSource, NSTableViewDelegate {
    let scroll = NSScrollView()
    private let table = NSTableView()
    var onJump: ((Int) -> Void)?
    var issues: [PopIssue] = [] { didSet { table.reloadData() } }

    override init() {
        super.init()
        for (id, title, width) in [("line", "line", 44), ("message", "error message", 250), ("near", "near", 160)] {
            let c = NSTableColumn(identifier: NSUserInterfaceItemIdentifier(id))
            c.title = title
            c.width = CGFloat(width)
            table.addTableColumn(c)
        }
        table.dataSource = self
        table.delegate = self
        table.usesAlternatingRowBackgroundColors = true
        table.columnAutoresizingStyle = .lastColumnOnlyAutoresizingStyle
        table.target = self
        table.doubleAction = #selector(clicked)
        scroll.documentView = table
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder
    }

    func numberOfRows(in tableView: NSTableView) -> Int { issues.count }

    func tableView(_ tableView: NSTableView, viewFor column: NSTableColumn?, row: Int) -> NSView? {
        let issue = issues[row]
        let id = column?.identifier.rawValue ?? ""
        let text = id == "line" ? (issue.line.map(String.init) ?? "–") : id == "message" ? issue.message : issue.near
        let cell = NSTextField(labelWithString: text)
        cell.lineBreakMode = .byTruncatingTail
        cell.toolTip = text
        if id != "message" { cell.font = .monospacedSystemFont(ofSize: 12, weight: .regular) }
        if id == "line" { cell.alignment = .right }
        return cell
    }

    @objc private func clicked() {
        let r = table.clickedRow
        if r >= 0, r < issues.count, let line = issues[r].line { onJump?(line) }
    }
}

/// The full log of the last render, for when the list is not enough.
final class PopLogWindow {
    private let window: NSPanel
    private let text: NSTextView

    init() {
        let scroll = NSTextView.scrollableTextView()
        text = scroll.documentView as! NSTextView
        text.isEditable = false
        text.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        window = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 680, height: 440),
                         styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        window.title = "Equation popup log"
        window.isReleasedWhenClosed = false
        window.level = .floating
        window.hidesOnDeactivate = false
        window.contentView = scroll
        window.setFrameAutosaveName("popLog")
    }

    func show(_ log: String) {
        text.string = log.isEmpty ? "(no log yet)" : log
        text.scrollToEndOfDocument(nil)
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
    }
}
