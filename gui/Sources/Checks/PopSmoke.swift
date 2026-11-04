import Cocoa

/// `pdfmdedit --smoke-pop`: the equation popup (it was eqpop), headless. The pure parts first (bracket pairing, the wrapper, the error
/// parser, the shortcut words, the settings that command line takes), then the file migration from an eqpop folder, then real renders
/// with the TeX that is installed (and pdfmd with typst, if both are), the window built and never shown (layout, settings, keys, the
/// copy to a private pasteboard), and the `colophon eq` command of the built program. Nothing appears on the screen, the user's
/// clipboard, settings and preamble are not touched (scratch domain, scratch folders).
/// `pdfmdedit --pop-screenshot OUT.png [--source TEXT] [--appearance light|dark] [--below] [--preamble]` draws the window off screen.
enum PopSmoke {
    static func spin(_ s: Double) { RunLoop.current.run(until: Date().addingTimeInterval(s)) }

    /// Scratch settings and folders; the folders are named in the environment before `PopStore` first reads it.
    static func scratch(_ name: String) -> (dir: URL, legacy: URL) {
        let domain = "io.github.aliperdehan.pdfmdedit." + name
        UserDefaults.standard.removePersistentDomain(forName: domain)
        Settings.store = UserDefaults(suiteName: domain)!
        let dir = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("pdfmdedit-\(name)-\(getpid())")
        let legacy = dir.appendingPathComponent("eqpop-old")
        try! FileManager.default.createDirectory(at: legacy, withIntermediateDirectories: true)
        setenv("COLOPHON_POP_HOME", dir.appendingPathComponent("home").path, 1)
        setenv("COLOPHON_POP_LEGACY", legacy.path, 1)
        return (dir, legacy)
    }

    static func run() {
        NSApplication.shared.setActivationPolicy(.prohibited)
        let (dir, legacy) = scratch("smokepop")
        let domain = "io.github.aliperdehan.pdfmdedit.smokepop"
        defer { UserDefaults.standard.removePersistentDomain(forName: domain); try? FileManager.default.removeItem(at: dir) }
        var failures = 0
        func check(_ name: String, _ ok: Bool, _ detail: String = "") {
            print("\(ok ? "ok  " : "FAIL") \(name) \(detail)")
            if !ok { failures += 1 }
        }
        let fm = FileManager.default

        // 1. brackets
        let s = "a{b[c]\\}d}(e" as NSString   // 0:a 1:{ 2:b 3:[ 4:c 5:] 6:\ 7:} 8:d 9:} 10:( 11:e
        check("a { pairs with the last }, skipping the escaped \\}", PopTeXEditing.partner(of: 1, in: s) == 9)
        check("a } pairs back to {", PopTeXEditing.partner(of: 9, in: s) == 1)
        check("[ pairs with ]", PopTeXEditing.partner(of: 3, in: s) == 5 && PopTeXEditing.partner(of: 5, in: s) == 3)
        check("an escaped brace and an unclosed ( have no partner", PopTeXEditing.partner(of: 7, in: s) == nil && PopTeXEditing.partner(of: 10, in: s) == nil)

        // 2. the wrapper and the error parser
        check("display wraps plain math in \\[ \\]", PopWrapper.body("x^2", .display) == "\\[\nx^2\n\\]")
        check("align* is left to bring its own math mode", PopWrapper.body("\\begin{align*}a&=b\\end{align*}", .display).hasPrefix("\\begin{align*}"))
        check("inline wraps in \\( \\)", PopWrapper.body("x", .inline) == "\\(x\\)")
        check("the Markdown wrapper hides the page number and keeps the source", PopWrapper.markdown("# Hi\n").contains("pagestyle{empty}") && PopWrapper.markdown("# Hi\n").hasSuffix("# Hi\n"))
        let log = "! Undefined control sequence.\n<argument> \\foo \nl.3 \\foo\n\n! Missing $ inserted.\nl.3 x\n"
        let found = PopWrapper.issues(log: log, source: "\\foo", mode: .display, prefix: 1)
        check("both errors of a log are listed", found.count == 2)
        check("an error on the first source line is line 1, with its text", found.first?.line == 1 && found.first?.near == "\\foo")
        let pre = PopWrapper.issues(log: "! Undefined control sequence.\nl.2 \\usepackage\n", source: "x", mode: .text, prefix: 3)
        check("an error above the source is marked as the preamble's", pre.first?.line == nil && pre.first?.message.hasPrefix("(preamble)") == true)
        check("an error at the closing \\] points at the last source line", PopWrapper.issues(log: "! Undefined control sequence.\nl.4 \\]\n", source: "\\foo", mode: .display, prefix: 1).first?.line == 1)
        check("blank lines trimmed from the top still count", PopWrapper.issues(log: "! Undefined control sequence.\nl.2 x\n", source: "\n\nx", mode: .text, prefix: 1).first?.line == 3)
        Settings.store.set(1, forKey: "popErrorsListed")
        check("the number of errors listed is a setting", PopWrapper.issues(log: log, source: "\\foo", mode: .display, prefix: 1).count == 1)
        Settings.store.removeObject(forKey: "popErrorsListed")
        Settings.store.set(3, forKey: "popBorderPt"); Settings.store.set(12.5, forKey: "popMaxWidthCm")
        check("the border and the widest line are settings", PopWrapper.header.contains("border=3pt,varwidth=12.5cm"), PopWrapper.header)
        Settings.store.removeObject(forKey: "popBorderPt"); Settings.store.removeObject(forKey: "popMaxWidthCm")
        check("the default class line is eqpop's", PopWrapper.header == "\\documentclass[border=2pt,varwidth=16cm]{standalone}\n")

        // 3. the shortcut, in symbols and in words, and what the settings command accepts
        check("⌥⇧T parses", PopShortcut.parse("⌥⇧T")?.label == "⌥⇧T" && PopShortcut.parse("⌥⇧T")?.code == 0x11)
        check("option+shift+t is the same", PopShortcut.parse("option+shift+t") == PopShortcut.parse("⌥⇧T"))
        check("alt-cmd-k becomes ⌥⌘K", PopShortcut.parse("alt-cmd-k")?.label == "⌥⌘K")
        check("ctrl+option+space", PopShortcut.parse("ctrl+option+space")?.label == "⌃⌥Space")
        check("⌘⌥F5", PopShortcut.parse("⌘⌥F5")?.label == "⌥⌘F5")
        check("a key alone is not a shortcut", PopShortcut.parse("T") == nil && PopShortcut.parse("shift+t") == nil)
        check("two keys are not a shortcut", PopShortcut.parse("option+a+b") == nil && PopShortcut.parse("option+") == nil)
        check("an unknown word is not a shortcut", PopShortcut.parse("hyper+t") == nil)
        check("the default setting is ⌥⇧T", PopShortcut.current()?.label == "⌥⇧T")
        Settings.store.set("none", forKey: "popHotkey")
        check("none means no shortcut", PopShortcut.current() == nil)
        Settings.store.removeObject(forKey: "popHotkey")
        let entries = SettingsCLI.entries()
        func entry(_ k: String) -> SettingsCLI.Entry { entries.first { $0.key == k }! }
        check("settings set popHotkey takes words and stores the symbols", SettingsCLI.parse(entry("popHotkey"), "cmd+option+K").value as? String == "⌥⌘K")
        check("settings set popHotkey refuses a bare key", SettingsCLI.parse(entry("popHotkey"), "k").error != nil)
        check("settings set popMode takes any case", SettingsCLI.parse(entry("popMode"), "TEXT").value as? String == "text")
        check("settings set popMode refuses a wrong word and names the choices", SettingsCLI.parse(entry("popMode"), "big").error?.contains("display, inline, text") == true)
        check("settings set popMenuBar on", (SettingsCLI.parse(entry("popMenuBar"), "on").value as? NSNumber)?.intValue == 1)
        check("every popup setting is on the Popup tab", entries.filter { $0.key.hasPrefix("pop") }.allSatisfy { $0.tab == "Popup" } && entries.filter { $0.key.hasPrefix("pop") }.count == Settings.items.filter { $0.key.hasPrefix("pop") }.count + Settings.texts.filter { $0.key.hasPrefix("pop") }.count)
        check("the popup's keys do not meet the editor's", Settings.items.filter { $0.key.hasPrefix("pop") }.allSatisfy { $0.key != "popLineNumbers" || $0.tab == "Popup" } && Settings.items.contains { $0.key == "lineNumbers" && $0.tab == "Editor" })

        // the Settings window stores a shortcut written out, and refuses a wrong one
        let prefs = PreferencesController()
        if let field = prefs.controls["popHotkey"] as? NSTextField {
            func fire(_ c: NSControl) { _ = c.sendAction(c.action, to: c.target) }
            field.stringValue = "alt+cmd+K"; fire(field)
            check("the Settings window stores a typed shortcut in its written-out form", Settings.store.string(forKey: "popHotkey") == "⌥⌘K", Settings.store.string(forKey: "popHotkey") ?? "nil")
            field.stringValue = "banana"; fire(field)
            check("and refuses a wrong one, showing what is stored", Settings.store.string(forKey: "popHotkey") == "⌥⌘K" && field.stringValue == "⌥⌘K", field.stringValue)
            field.stringValue = "none"; fire(field)
            check("none is kept as none", Settings.store.string(forKey: "popHotkey") == "none")
            Settings.store.removeObject(forKey: "popHotkey")
        } else { check("the Settings window has a shortcut field", false) }

        // 4. the files: copied from an eqpop folder the first time, never overwritten, never moved
        try! "% the old preamble\n\\usepackage{nulabreport}\n".write(to: legacy.appendingPathComponent("preamble.tex"), atomically: true, encoding: .utf8)
        check("the first use copies the eqpop preamble", PopStore.preamble().contains("the old preamble"))
        check("the metadata has no old file: the default is written", PopStore.metadata() == PopStore.defaultMetadata)
        check("the eqpop file is still there", fm.fileExists(atPath: legacy.appendingPathComponent("preamble.tex").path))
        try! "% edited here\n".write(to: PopStore.preambleURL, atomically: true, encoding: .utf8)
        try! "% changed in eqpop later\n".write(to: legacy.appendingPathComponent("preamble.tex"), atomically: true, encoding: .utf8)
        check("an existing preamble is not overwritten", PopStore.preamble() == "% edited here\n")
        try! fm.removeItem(at: PopStore.preambleURL)
        try! fm.removeItem(at: legacy.appendingPathComponent("preamble.tex"))
        check("with no old file the default preamble is written", PopStore.preamble() == PopStore.defaultPreamble)

        // 5. real renders with the TeX that is installed
        let tex = PopToolchain.find("pdflatex") != nil
        let renderer = PopRenderer()
        if tex {
            let req = PopRequest(source: "x^2 + y^2 = z^2", mode: .display, engine: .pdflatex, preamble: PopStore.preamble())
            let t0 = Date()
            switch renderer.renderSync(req) {
            case .success(let r):
                let size = PopPDFTools.pointSize(r.pdf)
                check("pdflatex renders a snippet to one cropped page", r.pages == 1 && (size?.width ?? 0) > 20 && (size?.width ?? 999) < 200 && (size?.height ?? 999) < 60,
                      "\(size.map { "\(Int($0.width)) x \(Int($0.height)) pt" } ?? "no size"), \(String(format: "%.1f", Date().timeIntervalSince(t0))) s")
                check("the result has PNG", PopPDFTools.png(from: r.pdf).map { $0.count > 100 } ?? false)
            case .failure(let e): check("pdflatex renders a snippet", false, "\(e)")
            }
            let bad = PopRequest(source: "\\foo", mode: .display, engine: .pdflatex, preamble: PopStore.preamble())
            if case .failure(.failed(let f)) = renderer.renderSync(bad) {
                check("an undefined command is listed on line 1", f.issues.first?.line == 1 && f.issues.first?.message.contains("Undefined control sequence") == true, "\(f.issues.map(\.message))")
            } else { check("an undefined command fails", false) }
            PopFormatCache.waitIdle()
            let t1 = Date()
            if case .success = renderer.renderSync(req) { check("the second render (cached preamble) is quicker", Date().timeIntervalSince(t1) < Date().timeIntervalSince(t0) + 0.5, String(format: "%.2f s", Date().timeIntervalSince(t1))) }
            else { check("the second render", false) }
        } else { print("skip pdflatex is not installed: the render checks") }
        if PopToolchain.find("typst") != nil, PdfmdTool.cachedResolve().best != nil {
            let md = PopRequest(source: "$E = m c^2$ and a list:\n\n- one\n- two", mode: .display, engine: .pdfmd, preamble: "", pdfmdEngine: "typst", metadata: "")
            let t = Date()
            switch renderer.renderSync(md) {
            case .success(let r):
                let size = PopPDFTools.pointSize(r.pdf)
                check("pdfmd (typst) renders a Markdown snippet, cropped", r.pages == 1 && (size?.height ?? 999) < 200, "\(size.map { "\(Int($0.width)) x \(Int($0.height)) pt" } ?? "-"), \(String(format: "%.1f", Date().timeIntervalSince(t))) s")
            case .failure(let e): check("pdfmd (typst) renders a Markdown snippet", false, "\(e)")
            }
        } else { print("skip pdfmd or typst is not installed: the Markdown render") }

        // 6. the window, built and never shown
        let c = PopController.shared
        c.offscreen = true
        let pb = NSPasteboard(name: NSPasteboard.Name("io.github.aliperdehan.pdfmdedit.smokepop.\(getpid())"))
        c.pasteboard = pb
        c.ensureBuilt()
        check("the window was not shown", c.panel.isVisible == false)
        c.panel.contentView?.layoutSubtreeIfNeeded()
        check("by default the preview is above the editor", c.preview.frame.midY > c.inputScroll.frame.midY, "\(Int(c.preview.frame.midY)) / \(Int(c.inputScroll.frame.midY))")
        Settings.set("popPreviewAbove", 0)
        c.settingsChanged()
        c.panel.contentView?.layoutSubtreeIfNeeded()
        check("popPreviewAbove 0 puts it below, in the open window", c.preview.frame.midY < c.inputScroll.frame.midY, "\(Int(c.preview.frame.midY)) / \(Int(c.inputScroll.frame.midY))")
        Settings.set("popLineNumbers", 0)
        c.settingsChanged()
        check("popLineNumbers 0 hides the line numbers of the popup", c.inputScroll.rulersVisible == false)
        check("and the editor's own line numbers are not touched", Settings.flag("lineNumbers"))
        let h0 = c.panel.frame.height
        Settings.set("popPreambleShown", 1)
        c.settingsChanged()
        check("popPreambleShown 1 opens the pane and grows the window by its height", !c.paneBox.isHidden && abs(c.panel.frame.height - h0 - (PopController.preamblePaneHeight + 8)) < 1, "\(h0) -> \(c.panel.frame.height)")
        Settings.set("popPreambleShown", 0)
        c.settingsChanged()
        check("and 0 closes it again to the same size", c.paneBox.isHidden && abs(c.panel.frame.height - h0) < 1)
        Settings.set("popMode", "inline"); Settings.set("popEngine", "lualatex"); Settings.set("popPdfmdEngine", "typst")
        c.settingsChanged()
        check("popMode, popEngine and popPdfmdEngine show in the open window", c.selectedMode == .inline && c.selectedEngine == .lualatex && c.pdfmdPopup.titleOfSelectedItem == "typst")
        Settings.store.removeObject(forKey: "popMode"); Settings.store.removeObject(forKey: "popEngine"); Settings.store.removeObject(forKey: "popPdfmdEngine")
        Settings.store.removeObject(forKey: "popPreviewAbove"); Settings.store.removeObject(forKey: "popLineNumbers")
        c.settingsChanged()
        check("back to the defaults", c.selectedMode == .display && c.selectedEngine == .pdflatex)

        func key(_ chars: String, _ mods: NSEvent.ModifierFlags) -> NSEvent {
            NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: mods, timestamp: 0, windowNumber: 0, context: nil,
                             characters: chars, charactersIgnoringModifiers: chars, isARepeat: false, keyCode: 0)!
        }
        check("command R is the popup's own", c.handleKey(key("r", .command)) == true)
        c.debounce?.invalidate()
        check("an unmodified r is not", c.handleKey(key("r", [])) == false)
        check("command K is not (the menu has it)", c.handleKey(key("k", .command)) == false)
        check("option command R is not (Show Build Log)", c.handleKey(key("r", [.command, .option])) == false)

        if tex {
            c.input.string = "E = mc^2"
            c.renderNow()
            check("the popup renders what is typed", PDFSmoke.wait(60) { c.lastPDF != nil && c.lastKey != nil }, c.status.stringValue)
            check("the preview shows it, with its size and time", c.preview.image != nil && c.status.stringValue.contains(" pt · "), c.status.stringValue)
            pb.clearContents()
            check("command return copies", c.handleKey(key("\r", .command)) == true)
            check("the copy holds PDF and PNG", pb.data(forType: .pdf) != nil && pb.data(forType: .png) != nil)
            check("the user's own clipboard was not used", c.pasteboard !== NSPasteboard.general)
            c.input.string = "\\foo"
            c.renderNow()
            check("a failing snippet shows the error table in place of the preview", PDFSmoke.wait(60) { !c.errors.scroll.isHidden } && c.preview.isHidden && c.errors.issues.first?.line == 1, c.status.stringValue)
            check("and the status says so", c.status.stringValue.contains("error"), c.status.stringValue)
            c.input.string = "line one\nline two\nline three"
            c.jump(toLine: 2)
            check("a double click on an error selects its line", (c.input.string as NSString).substring(with: c.input.selectedRange()).hasPrefix("line two"))
            PopFormatCache.waitIdle()
        }

        // 7. the icon's menu (the menu only: no icon is put in the menu bar by a test)
        Settings.set("popHideAfterCopy", 0)
        let menu = c.makeMenu()
        let hide = menu.items.first { $0.title == "Hide after copying" }
        check("the menu shows the settings as switches", hide?.state == .off && menu.items.first { $0.title == "Live preview" }?.state == .on)
        check("its first line names the shortcut", menu.items.first?.title == "Show Equation Popup  (⌥⇧T)", menu.items.first?.title ?? "")
        if let hide { c.toggleSetting(hide) }
        check("choosing a switch writes the setting", Settings.flag("popHideAfterCopy"))
        c.hotkeyNote = "⌥⇧T could not be registered"
        check("a shortcut that is held elsewhere is a line in the menu, not an alert", c.makeMenu().items.contains { $0.title.contains("could not be registered") && !$0.isEnabled })
        c.hotkeyNote = nil
        let hk = PopHotKey()
        let odd = PopShortcut.parse("⌃⌥⇧⌘F12")!
        check("a global shortcut registers and goes again", hk.register(odd) && { hk.unregister(); return true }(), "OSStatus \(hk.failure ?? 0)")

        // 8. `colophon eq`, from the built program
        let exe = CommandLine.arguments[0]
        func eq(_ args: [String], stdin: String? = nil) -> (status: Int32, out: String, err: String) {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: exe)
            p.arguments = args
            var env = ProcessInfo.processInfo.environment
            env["COLOPHON_CLI"] = "1"; env["COLOPHON_DOMAIN"] = domain
            for k in ["COLOPHON_POP_HOME", "COLOPHON_POP_LEGACY"] { if let v = getenv(k) { env[k] = String(cString: v) } }
            p.environment = env
            let o = Pipe(), e = Pipe(), i = Pipe()
            p.standardOutput = o; p.standardError = e; p.standardInput = i
            try? p.run()
            if let s = stdin { i.fileHandleForWriting.write(Data(s.utf8)) }
            i.fileHandleForWriting.closeFile()
            let od = o.fileHandleForReading.readDataToEndOfFile(), ed = e.fileHandleForReading.readDataToEndOfFile()
            p.waitUntilExit()
            return (p.terminationStatus, String(decoding: od, as: UTF8.self), String(decoding: ed, as: UTF8.self))
        }
        check("eq with no arguments says how to use it", eq(["eq"]).status == 2 && eq(["eq"]).err.contains("usage: colophon eq"))
        check("eq refuses an unknown engine", eq(["eq", "x", "o.pdf", "--engine", "word"]).status == 2)
        if tex {
            let out = dir.appendingPathComponent("eq out.pdf"), png = dir.appendingPathComponent("eq.png")
            let r = eq(["eq", "a^2", out.path, "--png", png.path])
            check("eq writes the PDF and the PNG", r.status == 0 && fm.fileExists(atPath: out.path) && fm.fileExists(atPath: png.path), r.err)
            let r2 = eq(["eq", "-", out.path, "--inline"], stdin: "\\alpha + \\beta")
            check("eq reads the snippet from the standard input", r2.status == 0, r2.err)
            let r3 = eq(["eq", "\\foo", out.path])
            check("eq reports an error with its line and exits 1", r3.status == 1 && r3.err.contains("line 1: Undefined control sequence"), r3.err)
            PopFormatCache.waitIdle()
        }

        print(failures == 0 ? "POP SMOKE OK" : "POP SMOKE FAILED (\(failures))")
        exit(failures == 0 ? 0 : 1)
    }

    /// `--pop-screenshot OUT.png`: the window drawn off screen on scratch settings, a scratch preamble and a sample text.
    static func screenshot(_ args: [String]) {
        NSApplication.shared.setActivationPolicy(.prohibited)
        guard let i = args.firstIndex(of: "--pop-screenshot"), i + 1 < args.count else { exit(2) }
        let (dir, _) = scratch("popshot")
        defer { UserDefaults.standard.removePersistentDomain(forName: "io.github.aliperdehan.pdfmdedit.popshot"); try? FileManager.default.removeItem(at: dir) }
        if let a = args.firstIndex(of: "--appearance"), a + 1 < args.count { NSApp.appearance = NSAppearance(named: args[a + 1] == "light" ? .aqua : .darkAqua) }
        if args.contains("--below") { Settings.store.set(0, forKey: "popPreviewAbove") }
        if args.contains("--preamble") { Settings.store.set(1, forKey: "popPreambleShown") }
        let c = PopController.shared
        c.offscreen = true
        c.ensureBuilt()
        c.input.string = args.firstIndex(of: "--source").map { args[$0 + 1] } ?? PopController.sample
        guard let rep = c.snapshot(), let png = rep.representation(using: .png, properties: [:]) else { print("no picture"); exit(1) }
        try! png.write(to: URL(fileURLWithPath: (args[i + 1] as NSString).expandingTildeInPath))
        PopFormatCache.waitIdle()
        print("wrote \(args[i + 1]) (\(rep.pixelsWide) x \(rep.pixelsHigh)): \(c.status.stringValue)")
    }
}
