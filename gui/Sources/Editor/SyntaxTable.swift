import Foundation

/// The syntax table: what the editor colours, written once in `lib/pdfmd_web/syntax/syntaxes.json` and read by the page's editor
/// (CodeMirror, `syntax/engine.js`) and by this one. The file's own header says what an engine must do; `Highlighter` does it here and
/// `pdfmdedit --smoke-syntax` runs `syntax/cases.json` through it (the Python test and the page run the same cases).
///
/// The table is found where the web page is: the app's `Resources/web/syntax/`, or the checkout's `lib/pdfmd_web/syntax/` next to a build
/// folder (`--web-root PATH` names the page's folder). Without it nothing is coloured, and a line on stderr says why.
struct SyntaxTable {
    struct Role {
        let key: String
        let category: String
        let light: String
        let dark: String
        let help: String
    }

    struct Rule {
        let regex: NSRegularExpression
        /// The role of the whole match, if the rule has one; `groups` are painted over it (group number, role).
        let role: String?
        let groups: [(Int, String)]
    }

    struct FrontMatter {
        let syntax: String
        let open: String
        let close: [String]
        let scan: Int
    }

    struct Fences {
        let markers: [String]
        let role: String
        /// Tried on the opening line of a block; its group 1 is the language word.
        let language: NSRegularExpression?
    }

    struct Syntax {
        let name: String
        let rules: [Rule]
        let frontMatter: FrontMatter?
        let fences: Fences?
        let extensions: [String]
        let languages: [String]
    }

    let roles: [Role]
    let syntaxes: [String: Syntax]

    /// The syntax of a file: the one whose `extensions` has the file's (lower case, no dot); markdown for a file no syntax claims.
    func name(forFileName fileName: String?) -> String {
        let ext = ((fileName ?? "") as NSString).pathExtension.lowercased()
        if !ext.isEmpty, let hit = syntaxes.first(where: { $0.value.extensions.contains(ext) }) { return hit.key }
        return "markdown"
    }

    /// The syntax that colours a fenced block, from the block's opening line (nil: none does, the block is one role).
    func language(of openingLine: String, in syntax: Syntax) -> Syntax? {
        guard let regex = syntax.fences?.language else { return nil }
        let ns = openingLine as NSString
        guard let m = regex.firstMatch(in: openingLine, options: [], range: NSRange(location: 0, length: ns.length)), m.numberOfRanges > 1,
              m.range(at: 1).location != NSNotFound else { return nil }
        let word = ns.substring(with: m.range(at: 1)).lowercased()
        return syntaxes.values.first { $0.languages.contains(word) }
    }

    static let shared: SyntaxTable = {
        guard let root = WebStudioController.webRoot() else {
            FileHandle.standardError.write(Data("pdfmdedit: the syntax table was not found (no web page folder): nothing is coloured\n".utf8))
            return SyntaxTable(roles: [], syntaxes: [:])
        }
        let url = root.appendingPathComponent("syntax/syntaxes.json")
        do {
            return try SyntaxTable(data: Data(contentsOf: url))
        } catch {
            FileHandle.standardError.write(Data("pdfmdedit: the syntax table \(url.path) cannot be read (\(error)): nothing is coloured\n".utf8))
            return SyntaxTable(roles: [], syntaxes: [:])
        }
    }()

    init(roles: [Role], syntaxes: [String: Syntax]) {
        self.roles = roles
        self.syntaxes = syntaxes
    }

    init(data: Data) throws {
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let roleList = root["roles"] as? [[String: String]],
              let syntaxMap = root["syntaxes"] as? [String: [String: Any]] else {
            throw NSError(domain: "SyntaxTable", code: 1, userInfo: [NSLocalizedDescriptionKey: "not a syntax table"])
        }
        roles = roleList.compactMap { r in
            guard let key = r["key"], let category = r["category"], let light = r["light"], let dark = r["dark"] else { return nil }
            return Role(key: key, category: category, light: light, dark: dark, help: r["help"] ?? "")
        }
        var built: [String: Syntax] = [:]
        for (name, raw) in syntaxMap {
            // every client sets the multiline option: ^ and $ are a line's start and end
            let rules: [Rule] = (raw["rules"] as? [[String: Any]] ?? []).compactMap { r in
                guard let match = r["match"] as? String,
                      let regex = try? NSRegularExpression(pattern: match, options: [.anchorsMatchLines]) else {
                    FileHandle.standardError.write(Data("pdfmdedit: syntax \(name): a pattern does not compile and is left out: \(r["match"] ?? "?")\n".utf8))
                    return nil
                }
                let groups = (r["groups"] as? [String: String] ?? [:]).compactMap { k, v in Int(k).map { ($0, v) } }.sorted { $0.0 < $1.0 }
                return Rule(regex: regex, role: r["role"] as? String, groups: groups)
            }
            var front: FrontMatter?
            if let f = raw["frontMatter"] as? [String: Any], let syntax = f["syntax"] as? String, let open = f["open"] as? String,
               let close = f["close"] as? [String], let scan = f["scan"] as? Int {
                front = FrontMatter(syntax: syntax, open: open, close: close, scan: scan)
            }
            var fences: Fences?
            if let f = raw["fences"] as? [String: Any], let markers = f["markers"] as? [String], let role = f["role"] as? String {
                fences = Fences(markers: markers, role: role, language: (f["language"] as? String).flatMap { try? NSRegularExpression(pattern: $0, options: []) })
            }
            built[name] = Syntax(name: name, rules: rules, frontMatter: front, fences: fences,
                                 extensions: raw["extensions"] as? [String] ?? [], languages: raw["languages"] as? [String] ?? [])
        }
        syntaxes = built
    }
}
