import Cocoa
import PDFKit

/// `pdfmdedit --smoke-build FILE.md`: command R in an editor window, against a stand-in for pdfmd (a small script that waits a
/// second, writes a PDF and prints pdfmd's `OK  a.md > a.pdf  in 1.0 s` line), so that it takes seconds and not a TeX run.
/// Checks that the text is saved before the build, that a path with a quote and spaces arrives whole, that the PDF the report line names
/// is found and shown (once: the automatic reload must not read it twice), that a command R during a build queues one more build, that
/// a failing command shows its log, that a build that runs too long is stopped with everything it started, and that a running
/// `pdfmd --watch` on the same file keeps the build from running twice. `--real` also builds with the pdfmd that is installed.
enum BuildSmoke {
    static func spin(_ s: Double) { RunLoop.current.run(until: Date().addingTimeInterval(s)) }

    static func run(_ path: String, real: Bool) {
        NSApplication.shared.setActivationPolicy(.prohibited)
        let domain = "io.github.aliperdehan.pdfmdedit.smokebuild"
        UserDefaults.standard.removePersistentDomain(forName: domain)
        Settings.store = UserDefaults(suiteName: domain)!
        Settings.store.set(100, forKey: "pdfReloadDebounceMs")
        defer { UserDefaults.standard.removePersistentDomain(forName: domain) }

        var failures = 0
        func check(_ name: String, _ ok: Bool, _ detail: String = "") {
            print("\(ok ? "ok  " : "FAIL") \(name) \(detail)")
            if !ok { failures += 1 }
        }
        let fm = FileManager.default
        let dir = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("pdfmdedit-smoke-build-\(getpid())")
        try! fm.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: dir) }

        // a file of parts/ is built as part of ../report.md: pdfmd's line names that source, and the PDF is beside it, not beside the part
        let partsDir = dir.appendingPathComponent("report-folder/parts")
        try! fm.createDirectory(at: partsDir, withIntermediateDirectories: true)
        let partial = dir.appendingPathComponent("report-folder/report.results.pdf")
        try! Data("%PDF".utf8).write(to: partial)
        let partsFile = partsDir.appendingPathComponent("45-results.md")
        let partialLine = "WARN something\nOK    ../report.md > report.results.pdf  in 45.4 s  (lualatex)\n"
        check("a partial build's PDF is found beside the report, not beside the part", PdfmdBuild.madeFile(output: partialLine, source: partsFile)?.standardizedFileURL.path == partial.standardizedFileURL.path,
              PdfmdBuild.madeFile(output: partialLine, source: partsFile)?.lastPathComponent ?? "nil")
        check("a plain build's PDF is still found beside the source", PdfmdBuild.madeFile(output: "OK    45-results.md > 45-results.pdf  in 1.0 s  (typst)\n", source: partsFile) == nil)

        // the stand-in for pdfmd and the PDF it "makes"
        let fixture = dir.appendingPathComponent("fixture.pdf")
        let pdf = PDFDocument()
        for _ in 0..<3 { pdf.insert(PDFPage(image: NSImage(size: NSSize(width: 200, height: 260), flipped: false) { r in NSColor.white.setFill(); r.fill(); return true })!, at: pdf.pageCount) }
        pdf.write(to: fixture)
        let script = dir.appendingPathComponent("fakepdfmd-marker.sh")
        try! """
        #!/bin/sh
        sleep "${FAKE_SLEEP:-1}"
        stem="${1%.*}"
        cp "$FAKE_FIXTURE" "$stem.pdf" || exit 3
        echo "OK    $(basename "$1") > $(basename "$stem").pdf  in 1.0 s  (stand-in)"
        """.write(to: script, atomically: true, encoding: .utf8)
        try! fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: script.path)
        setenv("FAKE_FIXTURE", fixture.path, 1)

        // pure parts: the report line, the watcher
        let src = URL(fileURLWithPath: "/x/doc.md")
        check("watcher: pdfmd --watch on this file", PdfmdBuild.watcher(for: src, listing: "  python3 /p/pdfmd.py --margin 1 --watch /x/doc.md\n/bin/zsh") != nil)
        check("watcher: pdfmd -w on this file", PdfmdBuild.watcher(for: src, listing: "python3 pdfmd.py -w doc.md") != nil)
        check("watcher: another file is not it", PdfmdBuild.watcher(for: src, listing: "python3 pdfmd.py --watch other.md") == nil)
        check("watcher: a plain build is not it", PdfmdBuild.watcher(for: src, listing: "python3 pdfmd.py doc.md") == nil)
        check("watcher: not pdfmd is not it", PdfmdBuild.watcher(for: src, listing: "tail --watch doc.md") == nil)

        // the document, with a name that a careless script would break on
        let md = dir.appendingPathComponent("it's a \"doc\" $x.md")
        try! fm.copyItem(at: URL(fileURLWithPath: path), to: md)
        guard let doc = Smoke.open(md), let c = doc.controller else { print("FAIL open"); exit(1) }
        let b = c.builder
        b.displayWindows = false
        b.commandOverride = script.path
        let tv = c.parts.textView
        func wait(_ t: Double, _ cond: () -> Bool) -> Bool { PDFSmoke.wait(t, cond) }
        func finishBuild(_ t: Double = 30) -> Bool { let n = b.builds; return wait(t) { b.builds > n && !b.running } }

        // 1. edited text is saved first, the path arrives whole, the PDF named by pdfmd is found and opened
        tv.insertText("SAVED-BEFORE-BUILD\n", replacementRange: NSRange(location: 0, length: 0))
        spin(0.3)   // the undo group closes, and the change count with it
        check("the document is edited", doc.isDocumentEdited)
        b.request()
        var sawRunning = false
        _ = wait(10) { sawRunning = b.running; return b.running }
        check("a build is running", sawRunning)
        check("the subtitle says Building", c.window?.subtitle.hasPrefix("Building") == true, c.window?.subtitle ?? "")
        check("the build finished", finishBuild(), b.lastResult.map { "status \($0.status) \($0.output)" } ?? "nil")
        let onDisk = (try? String(contentsOf: md, encoding: .utf8)) ?? ""
        check("the text was saved before the build", onDisk.hasPrefix("SAVED-BEFORE-BUILD"))
        check("the build succeeded with the odd file name", b.lastResult?.ok == true, b.lastResult?.output ?? "")
        let made = md.deletingPathExtension().appendingPathExtension("pdf")
        check("the PDF named in the report line is the one found", b.lastResult?.made?.standardizedFileURL.path == made.standardizedFileURL.path, b.lastResult?.made?.path ?? "nil")
        check("the subtitle says it was built", c.window?.subtitle.hasPrefix("Built") == true, c.window?.subtitle ?? "")
        func openViewer() -> PDFViewerDocument? { NSDocumentController.shared.documents.compactMap { $0 as? PDFViewerDocument }.first }
        _ = wait(5) { openViewer() != nil }
        let viewer = openViewer()
        check("the PDF was opened (setting buildOpensPDF)", viewer != nil)
        tv.insertText("x", replacementRange: NSRange(location: 0, length: 0))
        spin(0.3)
        check("editing clears the old build message", c.window?.subtitle == "", c.window?.subtitle ?? "")

        // 2. a second build while the PDF is open: shown again exactly once
        let before = viewer?.reloads ?? -1
        b.request()
        check("the second build finished", finishBuild())
        spin(1.5)   // the automatic reload's pause, and then some
        check("the open PDF was read again exactly once", viewer?.reloads == before + 1, "\(before) -> \(viewer?.reloads ?? -1)")

        // 3. command R during a build: one more build, however often it is pressed
        let n3 = b.builds
        b.request(); spin(0.3)
        b.request(); b.request(); b.request()
        check("the subtitle says the next build is queued", c.window?.subtitle.contains("queued") == true, c.window?.subtitle ?? "")
        _ = wait(30) { b.builds >= n3 + 2 && !b.running }
        spin(0.5)
        check("three presses during a build make exactly one more build", b.builds == n3 + 2, "builds \(b.builds - n3)")

        // 4. a failing command shows its log and says so
        b.commandOverride = "false"
        b.request()
        check("the failing build finished", finishBuild())
        check("it failed with status 1", b.lastResult?.ok == false && b.lastResult?.status == 1, "\(b.lastResult?.status ?? 99)")
        check("the subtitle says it failed", c.window?.subtitle.hasPrefix("Build failed") == true, c.window?.subtitle ?? "")
        check("the log has the command", b.log.string.contains("$ false"), b.log.string)
        tv.insertText("y", replacementRange: NSRange(location: 0, length: 0))
        spin(0.3)
        check("editing keeps a failure message", c.window?.subtitle.hasPrefix("Build failed") == true)

        // 5. a build that runs too long is stopped, with its children
        Settings.store.set(1, forKey: "buildTimeout")
        setenv("FAKE_SLEEP", "30", 1)
        b.commandOverride = script.path
        let t5 = Date()
        b.request()
        check("the long build finished (was stopped)", finishBuild(15))
        let took = Date().timeIntervalSince(t5)
        check("it was stopped by the timeout, not by running out", b.lastResult?.timedOut == true && took < 12, String(format: "%.1f s", took))
        check("the subtitle says why", c.window?.subtitle.contains("stopped after 1 s") == true, c.window?.subtitle ?? "")
        spin(0.5)
        let ps = Process(); ps.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep"); ps.arguments = ["-f", "fakepdfmd-marker"]
        let pipe = Pipe(); ps.standardOutput = pipe
        try? ps.run(); ps.waitUntilExit()
        let left = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
        check("nothing of the stopped build keeps running", left.isEmpty, left)
        Settings.store.removeObject(forKey: "buildTimeout")
        setenv("FAKE_SLEEP", "1", 1)

        // 6. a pdfmd --watch on the same file: command R only saves
        let watcher = Process()
        watcher.executableURL = URL(fileURLWithPath: "/bin/sh")
        watcher.arguments = ["-c", "sleep 60; :", "pdfmd", "--watch", md.lastPathComponent]
        try! watcher.run()
        spin(0.3)
        let n6 = b.builds
        tv.insertText("z", replacementRange: NSRange(location: 0, length: 0))
        spin(0.3)
        b.request()
        spin(2)
        check("with a watcher running, no build starts", b.builds == n6 && !b.running)
        check("and the subtitle says the watcher does it", c.window?.subtitle.contains("watching") == true, c.window?.subtitle ?? "")
        check("the text was saved all the same", ((try? String(contentsOf: md, encoding: .utf8)) ?? "").hasPrefix("zy"), String(((try? String(contentsOf: md, encoding: .utf8)) ?? "").prefix(10)))
        Settings.store.set(1, forKey: "buildWhenWatched")
        b.request()
        check("the setting builds all the same", finishBuild())
        watcher.terminate()
        watcher.waitUntilExit()

        // 7. no pdfmd at all: said, not silent
        b.commandOverride = nil
        Settings.store.set("definitely-not-a-pdfmd-command", forKey: "pdfmdCommand")
        b.request()
        check("a pdfmd command that does not answer is reported", finishBuild(40) && b.lastResult?.couldNotStart != nil && c.window?.subtitle.hasPrefix("Build failed") == true, c.window?.subtitle ?? "")
        Settings.store.removeObject(forKey: "pdfmdCommand")

        // 8. the pdfmd that is installed, in the environment a Dock launch has (run with env -i for that)
        if real {
            let tiny = dir.appendingPathComponent("real.md")
            try! "# Real build\n\nHello from the self-test.\n".write(to: tiny, atomically: true, encoding: .utf8)
            guard let rdoc = Smoke.open(tiny), let rc = rdoc.controller else { print("FAIL open real"); exit(1) }
            rc.builder.displayWindows = false
            rc.builder.request()
            let end = Date().addingTimeInterval(180)
            while rc.builder.builds == 0 && Date() < end { spin(0.1) }
            let r = rc.builder.lastResult
            print("   real build: status \(r?.status ?? -9), \(String(format: "%.1f", r?.seconds ?? 0)) s, made \(r?.made?.lastPathComponent ?? "nothing"), PATH \(ProcessInfo.processInfo.environment["PATH"] ?? "unset")")
            check("a real pdfmd build made a PDF", r?.ok == true && r?.made != nil, r?.output ?? "")
            rdoc.close()
        }

        doc.close()
        for d in NSDocumentController.shared.documents { d.close() }
        print(failures == 0 ? "BUILD SMOKE OK" : "BUILD SMOKE FAILED (\(failures))")
        exit(failures == 0 ? 0 : 1)
    }
}
