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
        let role: String
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
    }

    struct Syntax {
        let name: String
        let rules: [Rule]
        let frontMatter: FrontMatter?
        let fences: Fences?
    }

    let roles: [Role]
    let syntaxes: [String: Syntax]

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
            let rules: [Rule] = (raw["rules"] as? [[String: String]] ?? []).compactMap { r in
                guard let match = r["match"], let role = r["role"],
                      let regex = try? NSRegularExpression(pattern: match, options: [.anchorsMatchLines]) else {
                    FileHandle.standardError.write(Data("pdfmdedit: syntax \(name): a pattern does not compile and is left out: \(r["match"] ?? "?")\n".utf8))
                    return nil
                }
                return Rule(regex: regex, role: role)
            }
            var front: FrontMatter?
            if let f = raw["frontMatter"] as? [String: Any], let syntax = f["syntax"] as? String, let open = f["open"] as? String,
               let close = f["close"] as? [String], let scan = f["scan"] as? Int {
                front = FrontMatter(syntax: syntax, open: open, close: close, scan: scan)
            }
            var fences: Fences?
            if let f = raw["fences"] as? [String: Any], let markers = f["markers"] as? [String], let role = f["role"] as? String {
                fences = Fences(markers: markers, role: role)
            }
            built[name] = Syntax(name: name, rules: rules, frontMatter: front, fences: fences)
        }
        syntaxes = built
    }
}
