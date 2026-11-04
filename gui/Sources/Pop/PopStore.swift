import Foundation

/// What the equation popup keeps on disk (it was the separate app eqpop). The preamble is a plain file that the user owns: it is
/// written once, when missing, and never overwritten by the app; every render reads it from disk, so an edit in any editor counts
/// at once. `COLOPHON_POP_HOME` moves the folder (tests and screenshots); `COLOPHON_POP_LEGACY` names the folder of the old eqpop.
enum PopStore {
    private static var environment: [String: String] { ProcessInfo.processInfo.environment }

    static let appSupport: URL = {
        let dir: URL
        if let home = environment["COLOPHON_POP_HOME"], !home.isEmpty {
            dir = URL(fileURLWithPath: home, isDirectory: true)
        } else {
            let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            dir = base.appendingPathComponent("pdfmdedit/popup", isDirectory: true)   // beside the Themes folder
        }
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }()

    static let cacheDir: URL = {
        let dir: URL
        if environment["COLOPHON_POP_HOME"] != nil {
            dir = appSupport.appendingPathComponent("cache", isDirectory: true)
        } else {
            let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            dir = base.appendingPathComponent("io.github.aliperdehan.pdfmdedit/popup", isDirectory: true)
        }
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }()

    /// The folder of the standalone eqpop app, whose files are copied the first time (never moved: eqpop keeps working).
    static var legacy: URL {
        if let path = environment["COLOPHON_POP_LEGACY"], !path.isEmpty { return URL(fileURLWithPath: path, isDirectory: true) }
        return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("eqpop", isDirectory: true)
    }

    static var preambleURL: URL { appSupport.appendingPathComponent("preamble.tex") }
    static var metadataURL: URL { appSupport.appendingPathComponent("pdfmd-metadata.yaml") }

    static let defaultPreamble = """
    % Equation popup preamble: loaded before every snippet (no \\documentclass here; the class is standalone).
    % This file is yours. Colophon creates it once and never overwrites it.
    \\usepackage{amsmath,amssymb,bm}
    \\usepackage[version=4]{mhchem}
    \\usepackage{siunitx}
    \\usepackage{xcolor}
    % \\usepackage{chemfig}
    % \\newcommand{\\R}{\\mathbb{R}}

    """

    static let defaultMetadata = """
    # Equation popup: metadata for the pdfmd engine. It is written beside every Markdown snippet as metadata.yaml, where
    # pdfmd finds it like a project's own. This file is yours: Colophon creates it once and never overwrites it.
    # pdfmd-options:
    #   engine: typst
    # mainfont: STIX Two Text

    """

    /// Makes `url` exist: a copy of the eqpop file of the same name if there is one, else the default text. Reports which.
    @discardableResult
    static func create(_ url: URL, default text: String) -> String {
        let fm = FileManager.default
        if fm.fileExists(atPath: url.path) { return "kept" }
        let old = legacy.appendingPathComponent(url.lastPathComponent)
        if fm.fileExists(atPath: old.path), (try? fm.copyItem(at: old, to: url)) != nil { return "copied" }
        try? text.write(to: url, atomically: true, encoding: .utf8)
        return "default"
    }

    static func metadata() -> String {
        create(metadataURL, default: defaultMetadata)
        return (try? String(contentsOf: metadataURL, encoding: .utf8)) ?? defaultMetadata
    }

    static func preamble() -> String {
        create(preambleURL, default: defaultPreamble)
        return (try? String(contentsOf: preambleURL, encoding: .utf8)) ?? defaultPreamble
    }
}
