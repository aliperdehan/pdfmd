import Cocoa

/// One thing File > Export As can write. The table below is data: the menu, `colophon export --list` and the smoke test all read it, and
/// what each item does is only a pdfmd command line (`words`), so nothing here is a converter.
struct ExportFormat: Equatable {
    let id: String           // what `colophon export FILE ID` takes: "docx", "pdf", "pdf:typst", "md" ...
    let title: String        // the menu item
    let ext: String          // the extension of the file that is made (the file name may carry more: NAME.assembled.md)
    let words: [String]      // pdfmd's words after the file, without -o
    let engine: String?      // the program that must be there for it, as `pdfmd --check-dependencies` names it (nil: pandoc alone)
    let path: [String]       // the submenus below "Export As", [] = on the first level

    /// What the Save panel's title says: "Export as Cropped PDF" (the menu item alone, "PDF", would not tell it from the plain one).
    var panelTitle: String { path.first == "Cropped" ? "Cropped " + title : title }

    /// The name a Save panel proposes: the document's, with this format's extension.
    func fileName(for source: URL) -> String {
        let base = source.deletingPathExtension().lastPathComponent
        return id == "md" ? base + ".assembled.md" : base + "." + ext
    }
}

enum ExportTable {
    /// Every format, in menu order. `-t` is always written (also for PDF): an explicit target beats the extension of `-o`, and a `-t html` the
    /// user keeps in "pdfmd options for a build" is taken out of an export's words (`ExportArguments.withoutTarget`).
    static let all: [ExportFormat] = {
        var list: [ExportFormat] = []
        func add(_ path: [String], _ rows: [(id: String, title: String, ext: String)], engine: String? = nil, words: (String) -> [String] = { ["-t", $0] }) {
            for r in rows { list.append(ExportFormat(id: r.id, title: r.title, ext: r.ext, words: words(r.id), engine: engine, path: path)) }
        }
        // 1. standalone Markdown: pdfmd's own `--merge` (no -t: pdfmd refuses any target together with it)
        list.append(ExportFormat(id: "md", title: "Markdown (standalone)", ext: "md", words: ["--merge"], engine: nil, path: []))
        // 2. PDF, by engine
        list.append(ExportFormat(id: "pdf", title: "Auto", ext: "pdf", words: ["-t", "pdf"], engine: nil, path: ["PDF"]))
        func pdf(_ path: [String], _ family: (id: String, title: String)?, _ engines: [(id: String, title: String)]) {
            if let family { list.append(ExportFormat(id: "pdf:" + family.id, title: family.title, ext: "pdf", words: ["-t", "pdf", "-e", family.id], engine: nil, path: path)) }
            for e in engines { list.append(ExportFormat(id: "pdf:" + e.id, title: e.title, ext: "pdf", words: ["-t", "pdf", "-e", e.id], engine: e.id, path: path)) }
        }
        pdf(["PDF", "LaTeX"], ("tex", "Any"), [("lualatex", "LuaLaTeX"), ("xelatex", "XeLaTeX"), ("pdflatex", "pdfLaTeX"), ("latexmk", "latexmk"), ("tectonic", "Tectonic")])
        pdf(["PDF"], nil, [("typst", "Typst")])
        pdf(["PDF", "HTML"], ("html", "Any HTML"), [("weasyprint", "WeasyPrint"), ("wkhtmltopdf", "wkhtmltopdf"), ("pagedjs-cli", "Paged.js"), ("prince", "Prince")])
        pdf(["PDF", "HTML"], ("browser", "Any browser"), [])
        for b in [("chrome", "Chrome"), ("chromium", "Chromium"), ("edge", "Edge"), ("brave", "Brave")] {
            list.append(ExportFormat(id: "pdf:" + b.0, title: b.1, ext: "pdf", words: ["-t", "pdf", "-e", b.0], engine: nil, path: ["PDF", "HTML"]))   // pdfmd's report does not list browsers
        }
        pdf(["PDF", "Others"], nil, [("soffice", "LibreOffice"), ("calibre", "Calibre"), ("context", "ConTeXt"), ("groff", "groff"), ("pdfroff", "pdfroff"), ("inkmd", "inkmd (built in)"), ("md2pdf", "md2pdf")])
        // 3. the two that people mean most often
        add([], [("docx", "Word (.docx)", "docx")])
        add([], [("html", "HTML (.html)", "html")])
        // 3b. the pages cut to their ink (`--crop`), one submenu below HTML: a PDF stays vector with every page cut to its own ink; without
        // `--crop` a picture is the whole page
        list.append(ExportFormat(id: "pdf-cropped", title: "PDF", ext: "pdf", words: ["-t", "pdf", "--crop"], engine: nil, path: ["Cropped"]))
        list.append(ExportFormat(id: "svg-cropped", title: "SVG", ext: "svg", words: ["-t", "svg", "--crop"], engine: nil, path: ["Cropped"]))
        list.append(ExportFormat(id: "png-cropped", title: "PNG", ext: "png", words: ["-t", "png", "--crop"], engine: nil, path: ["Cropped"]))
        // 4. everything else pdfmd writes, by kind
        add(["Others", "Documents"], [("odt", "OpenDocument text (.odt)", "odt"), ("rtf", "Rich Text (.rtf)", "rtf"), ("fodt", "Flat OpenDocument (.fodt)", "fodt"),
                                       ("icml", "InDesign (.icml)", "icml")])
        add(["Others", "Documents"], [("doc", "Word 97 (.doc, through LibreOffice)", "doc")], engine: "soffice")
        add(["Others", "Slides"], [("pptx", "PowerPoint (.pptx)", "pptx"), ("revealjs", "reveal.js (.html)", "html"), ("slidy", "Slidy (.html)", "html"),
                                   ("slideous", "Slideous (.html)", "html"), ("s5", "S5 (.html)", "html"), ("dzslides", "DZSlides (.html)", "html"),
                                   ("beamer", "Beamer (LaTeX source, .tex)", "tex")])
        list.append(ExportFormat(id: "slides-pdf", title: "Beamer slides (PDF)", ext: "pdf", words: ["-t", "pdf", "-p"], engine: nil, path: ["Others", "Slides"]))
        add(["Others", "E-books"], [("epub", "EPUB (.epub)", "epub"), ("epub2", "EPUB 2 (.epub)", "epub"), ("fb2", "FictionBook (.fb2)", "fb2")])
        add(["Others", "E-books"], [("azw3", "Kindle AZW3 (.azw3)", "azw3"), ("mobi", "Mobipocket (.mobi)", "mobi"), ("kepub", "Kobo (.kepub.epub)", "kepub.epub"),
                                    ("lit", "Microsoft Reader (.lit)", "lit"), ("lrf", "Sony LRF (.lrf)", "lrf"), ("pdb", "Palm (.pdb)", "pdb"), ("rb", "Rocket eBook (.rb)", "rb"),
                                    ("snb", "Shanda Bambook (.snb)", "snb"), ("tcr", "TCR (.tcr)", "tcr"), ("pmlz", "Palm Markup (.pmlz)", "pmlz"),
                                    ("htmlz", "Zipped HTML (.htmlz)", "htmlz"), ("txtz", "Zipped text (.txtz)", "txtz")], engine: "calibre")
        add(["Others", "Web"], [("html4", "HTML 4 (.html)", "html"), ("html5", "HTML 5 (.html)", "html")])
        list.append(ExportFormat(id: "html:self-contained", title: "HTML, one file with the pictures and style inside", ext: "html",
                                 words: ["-t", "html", "--self-contained"], engine: nil, path: ["Others", "Web"]))
        add(["Others", "Plain text and Markdown"], [("txt", "Plain text (.txt)", "txt"), ("ascii", "ASCII text (.txt)", "txt"), ("gfm", "GitHub Markdown, flat (.md)", "md"),
                                                    ("gfm+raw", "GitHub Markdown with raw HTML (.md)", "md"), ("markdown", "Pandoc Markdown (.md)", "md"),
                                                    ("markdown_strict", "Original Markdown (.md)", "md"), ("markdown_mmd", "MultiMarkdown (.md)", "md"),
                                                    ("markdown_phpextra", "PHP Markdown Extra (.md)", "md"), ("commonmark", "CommonMark (.md)", "md"),
                                                    ("commonmark_x", "CommonMark with extensions (.md)", "md"), ("djot", "Djot (.dj)", "dj")])
        add(["Others", "Markup"], [("latex", "LaTeX source (.tex)", "tex"), ("typst", "Typst source (.typ)", "typ"), ("context", "ConTeXt source (.tex)", "tex"),
                                   ("texinfo", "Texinfo (.texi)", "texi"), ("rst", "reStructuredText (.rst)", "rst"), ("org", "Org mode (.org)", "org"),
                                   ("asciidoc", "AsciiDoc (.adoc)", "adoc"), ("textile", "Textile (.textile)", "textile"), ("mediawiki", "MediaWiki (.wiki)", "wiki"),
                                   ("dokuwiki", "DokuWiki (.txt)", "txt"), ("jira", "Jira (.txt)", "txt"), ("xwiki", "XWiki (.txt)", "txt"), ("zimwiki", "ZimWiki (.txt)", "txt"),
                                   ("muse", "Muse (.muse)", "muse"), ("man", "man page (.1)", "1"), ("ms", "groff ms (.ms)", "ms"), ("haddock", "Haddock (.haddock)", "haddock"),
                                   ("markua", "Markua (.md)", "md"), ("t2t", "txt2tags (.t2t)", "t2t"), ("vimdoc", "Vim help (.txt)", "txt"), ("bbcode", "BBCode (.bbcode)", "bbcode"), ("ansi", "ANSI terminal text (.ans)", "ans")])
        add(["Others", "XML and data"], [("docbook", "DocBook (.xml)", "xml"), ("jats", "JATS (.xml)", "xml"), ("tei", "TEI (.xml)", "xml"), ("opml", "OPML (.opml)", "opml"),
                                         ("json", "Pandoc AST (.json)", "json"), ("native", "Pandoc native (.native)", "native"), ("csljson", "CSL JSON (.json)", "json"),
                                         ("ipynb", "Jupyter notebook (.ipynb)", "ipynb"), ("bibtex", "BibTeX (.bib)", "bib"), ("biblatex", "BibLaTeX (.bib)", "bib")])
        add(["Others", "Pictures"], [("png", "PNG (.png)", "png"), ("jpg", "JPEG (.jpg)", "jpg"), ("tiff", "TIFF (.tiff)", "tiff"), ("svg", "SVG (.svg)", "svg"),
                                     ("eps", "EPS (.eps)", "eps"), ("ps", "PostScript (.ps)", "ps")])
        return list
    }()

    static func format(_ id: String) -> ExportFormat? { all.first { $0.id == id } }

    /// The writers of Pandoc that the menu does not list, each with the reason (the smoke test fails for a writer that is neither here nor
    /// in the table, so a new Pandoc writer is noticed). `colophon export FILE X` takes only the ids of the table; `colophon render FILE -t X`
    /// reaches every one of them.
    static let notOffered: [String: String] = [
        "asciidoc_legacy": "an older AsciiDoc dialect; asciidoc stands for it", "asciidoctor": "the same AsciiDoc; asciidoc stands for it",
        "bbcode_fluxbb": "one BBCode dialect; bbcode is the plain one", "bbcode_hubzilla": "one BBCode dialect; bbcode is the plain one",
        "bbcode_phpbb": "one BBCode dialect; bbcode is the plain one", "bbcode_steam": "one BBCode dialect; bbcode is the plain one",
        "bbcode_xenforo": "one BBCode dialect; bbcode is the plain one",
        "chunkedhtml": "writes a folder of pages, not a file", "docbook4": "docbook stands for it", "docbook5": "docbook stands for it",
        "epub3": "the same as epub", "jats_archiving": "jats stands for it", "jats_articleauthoring": "jats stands for it",
        "jats_publishing": "jats stands for it", "markdown_github": "Pandoc has deprecated it; gfm replaces it",
        "opendocument": "the flat XML of the same thing as fodt", "plain": "the same as txt", "xml": "Pandoc's own XML of the document tree; json and native say the same",
    ]

    /// The menu: submenus follow the `path` of the rows, in the order they first appear. Every leaf sends `exportAs:` along the responder
    /// chain (an editor window answers; nothing else does, so the items are grey in a PDF window) with the format's id.
    static func makeMenu(action: Selector = #selector(EditorWindowController.exportAs(_:))) -> NSMenu {
        let root = NSMenu(title: "Export As")
        var menus: [String: NSMenu] = ["": root]
        for f in all {
            var key = ""
            var parent = root
            for part in f.path {
                key += "/" + part
                if let m = menus[key] { parent = m; continue }
                let item = NSMenuItem(title: part, action: nil, keyEquivalent: "")
                let m = NSMenu(title: part)
                item.submenu = m
                parent.addItem(item)
                menus[key] = m
                parent = m
            }
            let item = NSMenuItem(title: f.title, action: action, keyEquivalent: "")
            item.representedObject = f.id
            parent.addItem(item)
        }
        return root
    }
}

// MARK: the words of the user's own pdfmd options

enum ExportArguments {
    /// The words of "pdfmd options for a build" without those that choose the target or the file: `-t X`, `--to X`, `--to=X`, `-tX`, `-o X`,
    /// `--out X`, `--output X` (and their `=` forms). pdfmd refuses `--merge` with any `-t`, and the export writes its own `-t` and `-o`.
    /// The words are cut at blanks outside quotes and keep their quotes, so the rest goes to the shell as it was typed.
    static func withoutTarget(_ text: String) -> String {
        var tokens: [String] = []
        var current = ""
        var quote: Character?
        for ch in text {
            if let q = quote {
                current.append(ch)
                if ch == q { quote = nil }
            } else if ch == "'" || ch == "\"" {
                quote = ch
                current.append(ch)
            } else if ch == " " || ch == "\t" || ch == "\n" {
                if !current.isEmpty { tokens.append(current); current = "" }
            } else {
                current.append(ch)
            }
        }
        if !current.isEmpty { tokens.append(current) }
        let takesValue: Set<String> = ["-t", "--to", "-o", "--out", "--output"]
        var kept: [String] = []
        var skip = false
        for t in tokens {
            if skip { skip = false; continue }
            if takesValue.contains(t) { skip = true; continue }
            if t.hasPrefix("--to=") || t.hasPrefix("--out=") || t.hasPrefix("--output=") { continue }
            if t.hasPrefix("-t"), !t.hasPrefix("--"), t.count > 2 { continue }
            if t.hasPrefix("-o"), !t.hasPrefix("--"), t.count > 2 { continue }
            kept.append(t)
        }
        return kept.joined(separator: " ")
    }
}

// MARK: which engines are there

/// What `pdfmd --check-dependencies` says about the programs behind the menu, read once, the first time the menu is looked at (the call takes
/// about a second). `OK` and anything it does not list stay enabled; only a `MISS` greys an item.
enum ExportAvailability {
    private(set) static var missing: Set<String> = []
    private(set) static var asked = false

    /// The names after `MISS`: `MISS  8. wkhtmltopdf` and `MISS  MathJax (math in ...)`.
    static func parse(_ report: String) -> Set<String> {
        var names = Set<String>()
        for raw in report.split(whereSeparator: \.isNewline) {
            let line = String(raw)
            guard line.hasPrefix("MISS"), let r = line.range(of: #"^MISS\s+(?:\d+\.\s+)?([A-Za-z0-9_+.-]+)"#, options: .regularExpression) else { continue }
            let words = line[r].split(whereSeparator: { $0 == " " || $0 == "\t" }).map(String.init)
            if let name = words.last { names.insert(name) }
        }
        return names
    }

    /// Starts the question in the background, once. The menu validates again each time it opens, so the answer shows without a signal.
    static func ensureLoaded() {
        guard !asked else { return }
        asked = true
        DispatchQueue.global().async {
            guard let command = PdfmdTool.cachedResolve().best?.command else { return }
            let report = PdfmdTool.run("eval \"$PDFMD_CMD --check-dependencies\" 2>&1", command: command, interactive: false, timeout: 30)
            let names = parse(report)
            DispatchQueue.main.async { missing = names }
        }
    }

    static func setForTest(_ names: Set<String>) { asked = true; missing = names }
}

// MARK: colophon export

/// `colophon export --list [--json]` and `colophon export FILE FORMAT [--engine E] [-o OUT]`: the menu without the window. It is
/// `colophon render FILE` with the words of the table, so a script or an agent writes the same files the menu does.
enum ExportCLI {
    static let usage = "usage: colophon export FILE FORMAT [--engine E] [-o OUT]   |   colophon export --list [--json]   (FORMAT: md, pdf, docx, html, odt, epub ... see --list)"

    static func list(json: Bool) -> Never {
        if json {
            let rows = ExportTable.all.map { f -> [String: Any] in
                ["id": f.id, "title": f.title, "extension": f.ext, "menu": f.path, "pdfmd": f.words, "needs": f.engine.map { $0 as Any } ?? NSNull()]
            }
            let data = (try? JSONSerialization.data(withJSONObject: rows, options: [.prettyPrinted, .sortedKeys])) ?? Data()
            CLI.out(String(decoding: data, as: UTF8.self))
        } else {
            for f in ExportTable.all {
                CLI.out(f.id.padding(toLength: 22, withPad: " ", startingAt: 0) + (".\(f.ext)").padding(toLength: 12, withPad: " ", startingAt: 0)
                        + (f.path + [f.title]).joined(separator: " > "))
            }
        }
        exit(0)
    }

    static func run(_ args: [String]) -> Never {
        if args.contains("--list") { list(json: args.contains("--json")) }
        var positional: [String] = []
        var engine: String?
        var out: String?
        var i = 0
        while i < args.count {
            switch args[i] {
            case "--engine", "-e", "-o", "--out":
                guard i + 1 < args.count else { CLI.fail("export: \(args[i]) needs a value") }
                if args[i] == "--engine" || args[i] == "-e" { engine = args[i + 1] } else { out = args[i + 1] }
                i += 1
            default: positional.append(args[i])
            }
            i += 1
        }
        guard positional.count == 2 else { CLI.fail(usage) }
        var id = positional[1]
        if let engine {
            guard id == "pdf" else { CLI.fail("export: --engine goes with the format pdf") }
            id = "pdf:" + engine
        }
        guard let f = ExportTable.format(id) else { CLI.fail("export: unknown format \(id) (colophon export --list)") }
        let file = URL(fileURLWithPath: (positional[0] as NSString).expandingTildeInPath).standardizedFileURL
        guard FileManager.default.fileExists(atPath: file.path) else { CLI.fail("export: no such file \(positional[0])") }
        let target = out.map { URL(fileURLWithPath: ($0 as NSString).expandingTildeInPath).standardizedFileURL }
            ?? file.deletingLastPathComponent().appendingPathComponent(f.fileName(for: file))
        if target.resolvingSymlinksInPath() == file.resolvingSymlinksInPath() { CLI.fail("export: the output would overwrite the source: \(file.lastPathComponent)", code: 1) }
        CLI.passthrough(tool: .pdfmd, [file.path] + f.words + ["-o", target.path])
    }
}
