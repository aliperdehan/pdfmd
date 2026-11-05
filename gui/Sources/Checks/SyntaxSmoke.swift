import Foundation

/// `pdfmdedit --smoke-syntax`: runs `syntax/cases.json` (the cases the Python test and the page's engine run too) through the editor's own colouring
/// pass (`Highlighter.pass`), on the whole text, and compares the runs with the expected ones. Offsets are UTF-16 units, which is NSString's own.
enum SyntaxSmoke {
    static func run() {
        guard let root = WebStudioController.webRoot(),
              let data = try? Data(contentsOf: root.appendingPathComponent("syntax/cases.json")),
              let file = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let cases = file["cases"] as? [[String: Any]] else {
            print("FAIL the cases were not found (syntax/cases.json next to the web page)")
            exit(1)
        }
        let table = SyntaxTable.shared
        var failed = 0
        print(table.syntaxes.isEmpty ? "FAIL the syntax table is empty" : "ok   the table has \(table.syntaxes.count) syntaxes and \(table.roles.count) roles")
        if table.syntaxes.isEmpty { failed += 1 }
        for c in cases {
            guard let name = c["name"] as? String, let syntaxName = c["syntax"] as? String, let text = c["text"] as? String,
                  let expected = c["runs"] as? [[Any]], let syntax = table.syntaxes[syntaxName] else { failed += 1; print("FAIL a case is malformed"); continue }
            let ns = text as NSString
            let fences = syntax.fences.map { Highlighter.fenceLines(in: ns, from: 0, to: ns.length, markers: $0.markers) } ?? []
            var owner = [String?](repeating: nil, count: ns.length)
            Highlighter.pass(ns, lo: 0, hi: ns.length, fences: fences, syntax: syntax, table: table) { role, r in
                for i in r.location..<(r.location + r.length) { owner[i] = role }
            }
            var runs: [[Any]] = []
            var at = 0
            while at < owner.count {
                let role = owner[at]
                var end = at + 1
                while end < owner.count && owner[end] == role { end += 1 }
                if let role { runs.append([at, end, role]) }
                at = end
            }
            let same = runs.count == expected.count && zip(runs, expected).allSatisfy { a, b in
                (a[0] as? Int) == (b[0] as? Int) && (a[1] as? Int) == (b[1] as? Int) && (a[2] as? String) == (b[2] as? String)
            }
            if !same { failed += 1 }
            print((same ? "ok   " : "FAIL ") + name + (same ? "" : "\n     got      \(runs)\n     expected \(expected)"))
        }
        print(failed == 0 ? "SMOKE OK" : "SMOKE FAILED (\(failed))")
        exit(failed == 0 ? 0 : 1)
    }
}
