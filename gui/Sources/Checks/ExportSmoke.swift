import Cocoa

/// `pdfmdedit --smoke-export`: File > Export As and `colophon export`.
/// The table and the menu (every row reachable, every pandoc writer either offered or named with the reason it is not), the words of the
/// user's own options that must not reach an export, the report of `--check-dependencies`, then an editor window exporting against a
/// stand-in for pdfmd (the words it gets, a path with a quote, a failure, a file that pdfmd did not write, an export that must not land
/// in the preview or open a viewer, a build refused while an export runs, the document itself never overwritten), and last the command
/// line with the pdfmd that is installed (markdown, docx, html and a typst PDF are really written and looked into).
enum ExportSmoke {
    static let domain = "io.github.aliperdehan.pdfmdedit.smokeexport"

    static func run() {
        NSApplication.shared.setActivationPolicy(.prohibited)
        UserDefaults.standard.removePersistentDomain(forName: domain)
        Settings.store = UserDefaults(suiteName: domain)!
        defer { UserDefaults.standard.removePersistentDomain(forName: domain) }
        var failures = 0
        func check(_ name: String, _ ok: Bool, _ detail: String = "") {
            print("\(ok ? "ok  " : "FAIL") \(name) \(detail)")
            if !ok { failures += 1 }
        }
        let fm = FileManager.default
        let dir = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("pdfmdedit-smoke-export-\(getpid())")
        try! fm.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: dir) }

        // 1. the table
        let all = ExportTable.all
        check("the table has rows", all.count > 80, "\(all.count)")
        check("every id is there once", Set(all.map(\.id)).count == all.count)
        check("every row has a title and an extension", all.allSatisfy { !$0.title.isEmpty && !$0.ext.isEmpty })
        check("every row but the standalone Markdown names its target with -t", all.filter { $0.id != "md" }.allSatisfy { $0.words.first == "-t" })
        check("the standalone Markdown is --merge and names no target (pdfmd refuses one)", ExportTable.format("md")?.words == ["--merge"])
        check("every PDF row says -t pdf, so a -t html of the user's cannot make HTML in a .pdf", all.filter { $0.id.hasPrefix("pdf") }.allSatisfy { Array($0.words.prefix(2)) == ["-t", "pdf"] })
        check("the cropped rows say --crop", ExportTable.format("pdf-cropped")?.words == ["-t", "pdf", "--crop"] && ExportTable.format("png-cropped")?.words == ["-t", "png", "--crop"] && ExportTable.format("svg-cropped")?.words == ["-t", "svg", "--crop"])
        check("an engine row passes -e with its id", ExportTable.format("pdf:typst")?.words == ["-t", "pdf", "-e", "typst"] && ExportTable.format("pdf:tex")?.words == ["-t", "pdf", "-e", "tex"])
        check("docx and html are on the first level", ExportTable.format("docx")?.path == [] && ExportTable.format("html")?.path == [])
        let source = URL(fileURLWithPath: "/x/My Report.md")
        check("the proposed names", ExportTable.format("docx")!.fileName(for: source) == "My Report.docx" && ExportTable.format("md")!.fileName(for: source) == "My Report.assembled.md"
              && ExportTable.format("kepub")!.fileName(for: source) == "My Report.kepub.epub")

        // the menu: every leaf sends exportAs: with an id of the table, each row once
        let menu = ExportTable.makeMenu()
        var leaves: [NSMenuItem] = []
        var submenus: [String] = []
        func walk(_ m: NSMenu) {
            for item in m.items {
                if let s = item.submenu { submenus.append(item.title); walk(s) } else { leaves.append(item) }
            }
        }
        walk(menu)
        check("the menu has a leaf for every row", leaves.count == all.count, "\(leaves.count) of \(all.count)")
        check("every leaf sends exportAs: with a known id", leaves.allSatisfy { $0.action == #selector(EditorWindowController.exportAs(_:)) && ExportTable.format($0.representedObject as? String ?? "") != nil })
        check("the first level is Markdown, PDF, Word, HTML, Cropped, Others", menu.items.map(\.title) == ["Markdown (standalone)", "PDF", "Word (.docx)", "HTML (.html)", "Cropped", "Others"], menu.items.map(\.title).joined(separator: ", "))
        check("PDF has the engines in submenus (a dropdown in a dropdown)", menu.items[1].submenu?.items.map(\.title).joined(separator: ",") == "Auto,LaTeX,Typst,HTML,Others" && submenus.contains("LaTeX") && submenus.contains("HTML"),
              menu.items[1].submenu?.items.map(\.title).joined(separator: ", ") ?? "")

        check("Cropped is one submenu of PDF, SVG, PNG (the cropped kinds are nowhere else)", menu.items[4].submenu?.items.map(\.title).joined(separator: ",") == "PDF,SVG,PNG"
              && all.filter { $0.id.hasSuffix("-cropped") }.allSatisfy { $0.path == ["Cropped"] } && all.filter { $0.id.hasSuffix("-cropped") }.count == 3)
        check("the Save panel names a cropped kind in full", ExportTable.format("pdf-cropped")?.panelTitle == "Cropped PDF" && ExportTable.format("pdf")?.panelTitle == "Auto")

        // every writer pandoc has is offered, or is named here with the reason it is not
        let pandocOnPath = PdfmdTool.run("whence -p pandoc", command: "", interactive: true, timeout: 8).trimmingCharacters(in: .whitespacesAndNewlines)
        if pandocOnPath.hasPrefix("/") {
            let writers = PdfmdTool.run("'\(pandocOnPath)' --list-output-formats", command: "", interactive: false, timeout: 8).split(whereSeparator: \.isNewline).map(String.init)
            let offered = Set(all.map(\.id))
            let unknown = writers.filter { !offered.contains($0) && ExportTable.notOffered[$0] == nil }
            check("every pandoc writer is offered or has a reason in ExportTable.notOffered", !writers.isEmpty && unknown.isEmpty, "not covered: \(unknown.joined(separator: " "))")
            check("every reason names a writer pandoc has (no stale rows)", ExportTable.notOffered.keys.allSatisfy { writers.contains($0) }, ExportTable.notOffered.keys.filter { !writers.contains($0) }.joined(separator: " "))
        } else {
            print("skip every pandoc writer is covered (no pandoc on the login shell's PATH)")
        }

        // 2. the user's own words
        func stripped(_ s: String) -> String { ExportArguments.withoutTarget(s) }
        check("-t X and --to X are taken out", stripped("-t html --engine typst") == "--engine typst" && stripped("--engine typst --to docx") == "--engine typst")
        check("--to=X, -tX, -o X, --out=X, --output X too", stripped("--to=html -tdocx -o a.pdf --out=b --output c -y m.yaml") == "-y m.yaml")
        check("quotes stay as they were typed", stripped("--css 'my style.css' -t html -V \"a b\"") == "--css 'my style.css' -V \"a b\"")
        check("empty stays empty and other flags stay", stripped("") == "" && stripped("--verbose --paper a4,landscape") == "--verbose --paper a4,landscape")
        check("--tex-like long options are not taken for -t", stripped("--toc --template x") == "--toc --template x")

        // 3. the report of --check-dependencies
        let report = """
        OK    pandoc  (/opt/homebrew/bin/pandoc)
        OK    1. lualatex  (/Library/TeX/texbin/lualatex)
        MISS  8. wkhtmltopdf
        MISS  9. pagedjs-cli
        MISS  10. prince
        OK    calibre (only when named: -e calibre)  (/opt/homebrew/bin/ebook-convert)
        MISS  MathJax (math in WeasyPrint's PDFs; pdfmd --install math:mathjax)
        MISS  md2pdf  (footnotes, bookmarks, math; pdfmd --install math)
        """
        check("MISS names are read, OK names and unlisted ones are not", ExportAvailability.parse(report) == ["wkhtmltopdf", "pagedjs-cli", "prince", "MathJax", "md2pdf"], ExportAvailability.parse(report).sorted().joined(separator: " "))

        // 4. an editor window exporting against a stand-in for pdfmd
        let fake = dir.appendingPathComponent("fakepdfmd-export.sh")
        try! """
        #!/bin/sh
        printf '%s\\n' "$@" > "$FAKE_LOG"
        sleep "${FAKE_SLEEP:-0}"
        if [ -n "$FAKE_EXIT" ]; then echo "something went wrong"; exit "$FAKE_EXIT"; fi
        out=""
        while [ $# -gt 0 ]; do [ "$1" = "-o" ] && out="$2"; shift; done
        if [ "$FAKE_WRITE" != "0" ]; then echo data > "$out"; fi
        echo "OK    x > $(basename "$out")  in 0.1 s"
        """.write(to: fake, atomically: true, encoding: .utf8)
        try! fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: fake.path)
        let log = dir.appendingPathComponent("args.log")
        setenv("FAKE_LOG", log.path, 1)
        func args() -> [String] { ((try? String(contentsOf: log, encoding: .utf8)) ?? "").split(separator: "\n", omittingEmptySubsequences: true).map(String.init) }

        let md = dir.appendingPathComponent("it's a \"doc\" $x.md")
        try! "# Title\n\nbody\n".write(to: md, atomically: true, encoding: .utf8)
        guard let doc = Smoke.open(md), let c = doc.controller else { print("FAIL open"); exit(1) }
        let ex = c.exporter
        ex.displayWindows = false
        ex.commandOverride = fake.path
        c.builder.displayWindows = false
        let tv = c.parts.textView
        func wait(_ t: Double, _ cond: () -> Bool) -> Bool { PDFSmoke.wait(t, cond) }
        func finishExport(_ t: Double = 30) -> Bool { let n = ex.exports; return wait(t) { ex.exports > n && !ex.running } }
        let outDocx = dir.appendingPathComponent("out it's \"here\".docx")
        var asked: (ExportFormat, URL)?
        ex.chooseOutput = { f, proposed in asked = (f, proposed); return outDocx }

        Settings.store.set("-t html --engine typst", forKey: "buildArguments")
        tv.insertText("SAVED-BEFORE-EXPORT\n", replacementRange: NSRange(location: 0, length: 0))
        spin(0.3)
        check("the document is edited", doc.isDocumentEdited)
        let builds = c.builder.builds
        ex.start(ExportTable.format("docx")!)
        check("the export finished", finishExport(), ex.lastResult.map { "status \($0.status) \($0.output)" } ?? "nil")
        let onDisk = (try? String(contentsOf: md, encoding: .utf8)) ?? ""
        check("the text was saved before the export", onDisk.hasPrefix("SAVED-BEFORE-EXPORT"))
        check("the Save panel got the document's name with .docx, in its folder", asked?.0.id == "docx" && asked?.1.lastPathComponent == "it's a \"doc\" $x.docx" && asked?.1.deletingLastPathComponent().resolvingSymlinksInPath().path == dir.resolvingSymlinksInPath().path, "\(asked?.0.id ?? "nil") \(asked?.1.lastPathComponent ?? "nil") | \(asked?.1.deletingLastPathComponent().resolvingSymlinksInPath().path ?? "nil") | \(dir.resolvingSymlinksInPath().path)")
        let a = args()
        check("the user's words, then the file whole, then the export's own", a.count == 7 && a[2] == md.path, a.joined(separator: " | "))
        check("then -t docx and -o with the path, whole", Array(a.suffix(4)) == ["-t", "docx", "-o", outDocx.path], a.joined(separator: " | "))
        check("the user's --engine typst is kept and their -t html is not", a.contains("typst") && !a.contains("html"), a.joined(separator: " | "))
        check("the file was made, and the subtitle says it", ex.lastOutput?.standardizedFileURL == outDocx.standardizedFileURL && c.window?.subtitle.hasPrefix("Exported") == true, c.window?.subtitle ?? "")
        check("an export is not a build", c.builder.builds == builds && c.builder.lastResult == nil)
        tv.insertText("x", replacementRange: NSRange(location: 0, length: 0))
        spin(0.3)
        check("editing clears the old message", c.window?.subtitle == "", c.window?.subtitle ?? "")

        // the standalone Markdown never gets a -t, whatever the user's options say
        let outMd = dir.appendingPathComponent("standalone.md")
        ex.chooseOutput = { _, _ in outMd }
        ex.start(ExportTable.format("md")!)
        _ = finishExport()
        let am = args()
        check("standalone Markdown: --merge, no -t, even with -t html in the options", am.contains("--merge") && !am.contains("-t") && !am.contains("html"), am.joined(separator: " | "))

        // a PDF export does not go to the preview pane, does not open a viewer, and an engine is passed with -e
        let outPdf = dir.appendingPathComponent("typeset.pdf")
        ex.chooseOutput = { _, _ in outPdf }
        Settings.store.set(1, forKey: "buildOpensPDF")
        ex.start(ExportTable.format("pdf:xelatex")!)
        _ = finishExport()
        spin(0.5)
        let ap = args()
        check("a PDF export: -t pdf -e xelatex -o OUT last, the user's -t html gone", Array(ap.suffix(6)) == ["-t", "pdf", "-e", "xelatex", "-o", outPdf.path] && !ap.contains("html"), ap.joined(separator: " | "))
        check("a PDF export opens no viewer and shows nothing in the preview", !NSDocumentController.shared.documents.contains { $0 is PDFViewerDocument } && !c.studio.isShown)

        // failure: the status, the log, no file
        setenv("FAKE_EXIT", "3", 1)
        ex.chooseOutput = { _, _ in dir.appendingPathComponent("never.odt") }
        ex.start(ExportTable.format("odt")!)
        check("the failing export finished", finishExport())
        check("it failed and says so", ex.lastResult?.status == 3 && ex.lastOutput == nil && c.window?.subtitle.hasPrefix("Export failed") == true, c.window?.subtitle ?? "")
        check("the log has the command and what pdfmd said", c.builder.log.string.contains("$ ") && c.builder.log.string.contains("something went wrong"), c.builder.log.string)
        unsetenv("FAKE_EXIT")

        // a stale file of an earlier export is not a success when pdfmd wrote nothing
        let stale = dir.appendingPathComponent("stale.rtf")
        try! "old".write(to: stale, atomically: true, encoding: .utf8)
        try! fm.setAttributes([.modificationDate: Date(timeIntervalSinceNow: -3600)], ofItemAtPath: stale.path)
        ex.chooseOutput = { _, _ in stale }
        let noOK = dir.appendingPathComponent("noreport.sh")
        try! "#!/bin/sh\nexit 0\n".write(to: noOK, atomically: true, encoding: .utf8)
        try! fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: noOK.path)
        ex.commandOverride = noOK.path
        ex.start(ExportTable.format("rtf")!)
        check("the quiet export finished", finishExport())
        check("an old file at that path is not taken for the result", ex.lastOutput == nil && c.window?.subtitle.hasPrefix("Export failed (pdfmd wrote no file)") == true, c.window?.subtitle ?? "")
        ex.commandOverride = fake.path

        // a picture format of several pages: pdfmd writes a folder named like the file, and that is what was made
        let pages = dir.appendingPathComponent("pages.png")
        let folderScript = dir.appendingPathComponent("folder.sh")
        try! """
        #!/bin/sh
        out=""
        while [ $# -gt 0 ]; do [ "$1" = "-o" ] && out="$2"; shift; done
        d="${out%.*}"
        mkdir -p "$d" && echo x > "$d/001.png" && echo x > "$d/002.png"
        echo "OK    x.md > $(basename "$d")/002.png"
        """.write(to: folderScript, atomically: true, encoding: .utf8)
        try! fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: folderScript.path)
        ex.commandOverride = folderScript.path
        ex.chooseOutput = { _, _ in pages }
        ex.start(ExportTable.format("png-cropped")!)
        check("the picture export finished", finishExport())
        check("several pages: the folder is the result, and the subtitle says so", ex.lastOutput?.lastPathComponent == "pages" && c.window?.subtitle.contains("one picture per page") == true, "\(ex.lastOutput?.path ?? "nil") \(c.window?.subtitle ?? "")")
        ex.commandOverride = fake.path

        // the document itself is never overwritten
        let before = args()
        ex.chooseOutput = { _, _ in md }
        ex.start(ExportTable.format("gfm")!)
        spin(0.5)
        check("an output that is the document itself is refused, pdfmd does not run", args() == before && !ex.running && c.window?.subtitle.hasPrefix("Not exported") == true, c.window?.subtitle ?? "")

        // a build is refused while an export runs, and the other way round
        setenv("FAKE_SLEEP", "2", 1)
        ex.chooseOutput = { _, _ in dir.appendingPathComponent("slow.html") }
        let n = c.builder.builds
        ex.start(ExportTable.format("html")!)
        spin(0.3)
        check("the export is running", ex.running)
        c.builder.request()
        spin(0.3)
        check("a build while an export runs is refused", !c.builder.running && c.builder.builds == n && c.window?.subtitle.hasPrefix("Exporting") == true, c.window?.subtitle ?? "")
        let ran = ex.exports
        ex.start(ExportTable.format("txt")!)
        check("a second export while one runs does nothing", ex.exports == ran && ex.running)
        check("the first one finished", finishExport())
        unsetenv("FAKE_SLEEP")

        // 5. the command line, with the pdfmd that is installed
        let list = CLISmoke.colophon(["export", "--list", "--json"], extra: ["COLOPHON_DOMAIN": domain])
        let rows = (try? JSONSerialization.jsonObject(with: Data(list.out.utf8))) as? [[String: Any]]
        check("export --list --json is the table", rows?.count == all.count && rows?.first?["id"] as? String == "md", "\(rows?.count ?? -1)")
        let text = CLISmoke.colophon(["export", "--list"], extra: ["COLOPHON_DOMAIN": domain])
        check("export --list shows menu paths", text.out.contains("PDF > LaTeX > LuaLaTeX") && text.out.contains("Others > Documents"), text.out.prefix(80).description)
        check("an unknown format is an error", CLISmoke.colophon(["export", md.path, "nonsense"], extra: ["COLOPHON_DOMAIN": domain]).status == 2)
        check("--engine is only for pdf", CLISmoke.colophon(["export", md.path, "docx", "--engine", "typst"], extra: ["COLOPHON_DOMAIN": domain]).status == 2)
        check("the document itself is refused on the command line", CLISmoke.colophon(["export", md.path, "md", "-o", md.path], extra: ["COLOPHON_DOMAIN": domain]).status == 1)
        check("no file is an error", CLISmoke.colophon(["export", dir.appendingPathComponent("none.md").path, "docx"], extra: ["COLOPHON_DOMAIN": domain]).status == 2)

        let realCheck = CLISmoke.colophon(["check", "--json"], extra: ["COLOPHON_DOMAIN": domain])
        if realCheck.out.contains("\"pdfmd\"") && !realCheck.out.contains("not found") {
            let real = dir.appendingPathComponent("real doc.md")
            try! "---\ntitle: Real\n---\n\n# Heading\n\nText with math $x^2$.\n".write(to: real, atomically: true, encoding: .utf8)
            func export(_ id: String, _ out: String, extra: [String] = []) -> (CLISmoke.Answer, URL) {
                let url = dir.appendingPathComponent(out)
                return (CLISmoke.colophon(["export", real.path, id, "-o", url.path] + extra, extra: ["COLOPHON_DOMAIN": domain]), url)
            }
            func head(_ url: URL, _ n: Int = 4) -> String { String(decoding: ((try? Data(contentsOf: url)) ?? Data()).prefix(n), as: UTF8.self) }
            let (m, mu) = export("md", "real.assembled.md")
            check("real: standalone Markdown", m.status == 0 && ((try? String(contentsOf: mu, encoding: .utf8)) ?? "").contains("Heading"), m.err)
            let (d, du) = export("docx", "real.docx")
            check("real: docx is a zip", d.status == 0 && head(du, 2) == "PK", d.err)
            let (h, hu) = export("html", "real.html")
            check("real: html", h.status == 0 && ((try? String(contentsOf: hu, encoding: .utf8)) ?? "").contains("Heading"), h.err)
            let (p, pu) = export("pdf", "real.pdf", extra: ["--engine", "typst"])
            check("real: PDF through typst", p.status == 0 && head(pu) == "%PDF", p.err)
            let (t, tu) = export("txt", "real.txt")
            check("real: plain text", t.status == 0 && ((try? String(contentsOf: tu, encoding: .utf8)) ?? "").contains("Heading"), t.err)
        } else {
            print("skip real exports (no pdfmd found)")
        }

        print(failures == 0 ? "EXPORT SMOKE OK" : "EXPORT SMOKE FAILED (\(failures))")
        exit(failures == 0 ? 0 : 1)
    }

    static func spin(_ s: Double) { RunLoop.current.run(until: Date().addingTimeInterval(s)) }
}
