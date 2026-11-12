import Foundation

/// `colophon eq SNIPPET OUT.pdf [--display|--inline|--text] [--engine pdflatex|lualatex|xelatex|pdfmd] [--pdfmd-engine E] [--metadata FILE]
/// [--preamble FILE] [--png FILE] [--svg FILE] [--warm]`: the equation popup's pipeline without its window (for scripts and for an agent).
/// SNIPPET `-` reads the snippet from the standard input. What is not given comes from the settings (`popMode`, `popEngine`,
/// `popPdfmdEngine`) and from the popup's preamble file.
enum PopCLI {
    static let usage = "usage: colophon eq SNIPPET OUT.pdf [--display|--inline|--text] [--engine E] [--pdfmd-engine E] [--metadata FILE] [--preamble FILE] [--png FILE] [--svg FILE] [--warm]   (SNIPPET - reads the standard input)"

    static func run(_ args: [String]) -> Never {
        var positional: [String] = []
        var mode = PopMode(rawValue: Settings.string("popMode")) ?? .display
        var engine = PopEngine(rawValue: Settings.string("popEngine")) ?? .pdflatex
        var pdfmdEngine = Settings.string("popPdfmdEngine")
        var preamble: String?
        var metadata: String?
        var pngPath: String?
        var svgPath: String?
        var warm = false
        func path(_ s: String) -> String { (s as NSString).expandingTildeInPath }
        func text(_ s: String) -> String {
            guard let t = try? String(contentsOfFile: path(s), encoding: .utf8) else { CLI.fail("eq: cannot read \(s)") }
            return t
        }
        var i = 0
        while i < args.count {
            let a = args[i]
            switch a {
            case "--display": mode = .display
            case "--inline": mode = .inline
            case "--text": mode = .text
            case "--warm": warm = true
            case "--engine", "--preamble", "--png", "--svg", "--pdfmd-engine", "--metadata":
                guard i + 1 < args.count else { CLI.fail("eq: \(a) needs a value") }
                i += 1
                let v = args[i]
                switch a {
                case "--engine":
                    guard let e = PopEngine(rawValue: v) else { CLI.fail("eq: unknown engine \(v) (\(PopEngine.allCases.map(\.rawValue).joined(separator: ", ")))") }
                    engine = e
                case "--pdfmd-engine":
                    guard popPdfmdEngines.contains(v) else { CLI.fail("eq: --pdfmd-engine is one of \(popPdfmdEngines.joined(separator: ", "))") }
                    pdfmdEngine = v
                case "--metadata": metadata = text(v)
                case "--preamble": preamble = text(v)
                case "--png": pngPath = path(v)
                default: svgPath = path(v)
                }
            default: positional.append(a)
            }
            i += 1
        }
        guard positional.count == 2 else { CLI.fail(usage) }
        var snippet = positional[0]
        if snippet == "-" { snippet = String(decoding: FileHandle.standardInput.readDataToEndOfFile(), as: UTF8.self) }
        let req = PopRequest(source: snippet, mode: mode, engine: engine, preamble: preamble ?? PopStore.preamble(),
                             pdfmdEngine: pdfmdEngine, metadata: metadata ?? PopStore.metadata())
        switch PopRenderer().renderSync(req) {
        case .success(let rendered):
            let pdf = rendered.pdf
            if rendered.pages > 1 { CLI.err("colophon: the engine made \(rendered.pages) pages; only the first is kept") }
            if warm { PopFormatCache.waitIdle() }   // lets the cached preamble finish, so the next run is fast
            do {
                try pdf.write(to: URL(fileURLWithPath: path(positional[1])))
                if let p = pngPath {
                    guard let png = PopPDFTools.png(from: pdf) else { throw CocoaError(.fileWriteUnknown) }
                    try png.write(to: URL(fileURLWithPath: p))
                }
                if let p = svgPath {
                    guard let svg = try PopPDFTools.svg(from: pdf) else { CLI.fail("eq: SVG needs pdftocairo (brew install poppler) or mutool (brew install mupdf-tools)", code: 1) }
                    try svg.write(to: URL(fileURLWithPath: p))
                }
            } catch { CLI.fail("eq: \(error.localizedDescription)", code: 1) }
            exit(0)
        case .failure(.noEngine(let name)):
            CLI.fail("eq: \(name) not found", code: 1)
        case .failure(.failed(let f)):
            for issue in f.issues {
                let at = issue.line.map { "line \($0): " } ?? ""
                CLI.err("colophon: eq: \(at)\(issue.message)\(issue.near.isEmpty ? "" : "   near: " + issue.near)")
            }
            exit(1)
        case .failure(.cancelled):
            exit(1)
        }
    }
}
