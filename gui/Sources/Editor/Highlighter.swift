import Cocoa

/// Colours for Markdown source, built so that typing never waits for it:
///  * colours are layout-manager TEMPORARY attributes: the text storage is never touched, so a colour pass
///    cannot invalidate layout or enter the undo stack;
///  * only the visible lines plus a margin (a setting) are coloured; scrolling colours the new lines on demand;
///  * the one thing that needs the whole document, "is this line inside a code fence?", is a sorted list of the
///    fence lines, kept up to date by shifting it on every edit and rescanning only the edited lines.
/// Known limits (alpha): a fence is closed by any fence line (parity), not by a matching one; inline rules are
/// line-local; the colour pass runs on the main thread, bounded by the margin, not on a background queue.
final class Highlighter: NSObject, NSTextStorageDelegate {
    /// What is coloured, and in which role, is the syntax table's business (`SyntaxTable`, lib/pdfmd_web/syntax/syntaxes.json, read by the page's
    /// editor too); a colour is looked up when the pass paints, so the theme is never baked into the rules.
    private let table = SyntaxTable.shared
    private(set) var syntax: SyntaxTable.Syntax?

    private weak var textView: NSTextView?
    private var fences: [Int] = []        // offsets of the fence lines (``` or ~~~), sorted
    private var colored = NSRange(location: NSNotFound, length: 0)
    private var pending: DispatchWorkItem?
    var enabled = true
    /// Seconds each colour pass took, for the benchmark.
    var passSeconds: [Double] = []

    init(_ tv: NSTextView, syntax name: String = "markdown") {
        syntax = SyntaxTable.shared.syntaxes[name]
        super.init()
        textView = tv
        tv.textStorage?.delegate = self
        if let clip = tv.enclosingScrollView?.contentView {
            clip.postsBoundsChangedNotifications = true
            NotificationCenter.default.addObserver(self, selector: #selector(scrolled), name: NSView.boundsDidChangeNotification, object: clip)
        }
    }

    deinit { NotificationCenter.default.removeObserver(self) }

    // MARK: edits

    func textStorage(_ ts: NSTextStorage, didProcessEditing mask: NSTextStorageEditActions, range: NSRange, changeInLength delta: Int) {
        guard mask.contains(.editedCharacters) else { return }
        let ns = ts.mutableString
        let n = ns.length
        let newStart = ns.lineRange(for: NSRange(location: min(range.location, n), length: 0)).location
        let newEnd = NSMaxRange(ns.lineRange(for: NSRange(location: min(NSMaxRange(range), n), length: 0)))
        let oldEnd = max(newStart, newEnd - delta)
        let a = lowerBound(newStart)
        let b = max(a, lowerBound(oldEnd))
        for i in b..<fences.count { fences[i] += delta }
        fences.removeSubrange(a..<b)
        fences.insert(contentsOf: Highlighter.fenceLines(in: ns, from: newStart, to: newEnd, markers: syntax?.fences?.markers ?? []), at: a)

        // keep the "already coloured" range roughly right so scrolling decides correctly
        if colored.location != NSNotFound {
            if range.location >= NSMaxRange(colored) {
            } else if NSMaxRange(range) - delta <= colored.location {
                colored.location = max(0, colored.location + delta)
            } else {
                colored.length = max(0, colored.length + delta)
            }
        }
        schedule(afterMs: Settings.int("highlightDelayMs"))
    }

    /// Offsets of the lines in `from..<to` that open or close a code fence (up to three spaces, then one of the table's markers).
    static func fenceLines(in ns: NSString, from: Int, to: Int, markers: [String]) -> [Int] {
        var found = Set<Int>()
        for marker in markers {
            let width = (marker as NSString).length
            var p = from
            while p < to {
                let hit = ns.range(of: marker, options: .literal, range: NSRange(location: p, length: to - p))
                if hit.location == NSNotFound { break }
                var q = hit.location
                var spaces = 0
                while q > 0 && spaces < 3 && ns.character(at: q - 1) == 0x20 { q -= 1; spaces += 1 }
                if q == 0 || ns.character(at: q - 1) == 0x0A || ns.character(at: q - 1) == 0x0D { found.insert(q) }
                p = hit.location + width
            }
        }
        return found.sorted()
    }

    /// Index of the first fence at or after `offset`.
    private func lowerBound(_ offset: Int) -> Int { Highlighter.lowerBound(fences, offset) }

    private static func lowerBound(_ fences: [Int], _ offset: Int) -> Int {
        var lo = 0, hi = fences.count
        while lo < hi {
            let mid = (lo + hi) / 2
            if fences[mid] < offset { lo = mid + 1 } else { hi = mid }
        }
        return lo
    }

    // MARK: scheduling

    @objc private func scrolled() {
        guard enabled, let visible = visibleCharacters() else { return }
        if colored.location == NSNotFound || NSIntersectionRange(visible, colored).length < visible.length {
            schedule(afterMs: Settings.int("scrollDelayMs"))
        }
    }

    private func schedule(afterMs: Int) {
        pending?.cancel()
        let item = DispatchWorkItem { [weak self] in self?.highlightNow() }
        pending = item
        DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(max(0, afterMs)), execute: item)
    }

    private func visibleCharacters() -> NSRange? {
        guard let tv = textView else { return nil }
        if let tlm = tv.textLayoutManager {   // TextKit 2
            // Asked of the scroll position, not of the layout controller's viewport: the viewport is only updated when the
            // view draws, so right after a scroll it still names the old place (measured: 0 coloured pixels far down).
            let tcm = tlm.textContentManager!
            let origin = tv.textContainerOrigin
            let rect = tv.visibleRect.offsetBy(dx: -origin.x, dy: -origin.y)
            guard let top = tlm.textLayoutFragment(for: CGPoint(x: 1, y: max(0, rect.minY))),
                  let bottom = tlm.textLayoutFragment(for: CGPoint(x: 1, y: max(0, rect.maxY - 1))) ?? Optional(top) else { return nil }
            let start = tcm.offset(from: tcm.documentRange.location, to: top.rangeInElement.location)
            let end = tcm.offset(from: tcm.documentRange.location, to: bottom.rangeInElement.endLocation)
            return NSRange(location: start, length: max(0, end - start))
        }
        guard let lm = tv.layoutManager, let container = tv.textContainer else { return nil }   // TextKit 1
        let origin = tv.textContainerOrigin
        let rect = tv.visibleRect.offsetBy(dx: -origin.x, dy: -origin.y)
        let glyphs = lm.glyphRange(forBoundingRect: rect, in: container)
        return lm.characterRange(forGlyphRange: glyphs, actualGlyphRange: nil)
    }

    // MARK: the pass

    func highlightNow() {
        pending?.cancel()
        guard enabled, let syntax, let tv = textView, let storage = tv.textStorage else { return }
        let ns = storage.mutableString
        let n = ns.length
        let maxMB = Settings.number("highlightMaxMB")
        if n == 0 || (maxMB > 0 && Double(n) > maxMB * 1_000_000) { return }
        let started = DispatchTime.now().uptimeNanoseconds

        guard let visible = visibleCharacters() else { return }
        let margin = Settings.int("highlightMarginLines")
        var lo = visible.location, hi = NSMaxRange(visible)
        for _ in 0..<margin {
            if lo <= 0 { break }
            lo = ns.lineRange(for: NSRange(location: lo - 1, length: 0)).location
        }
        for _ in 0..<margin {
            if hi >= n { break }
            hi = NSMaxRange(ns.lineRange(for: NSRange(location: hi, length: 0)))
        }
        lo = max(0, lo); hi = min(n, hi)
        let range = NSRange(location: lo, length: hi - lo)

        removeColors(range)
        Highlighter.pass(ns, lo: lo, hi: hi, fences: fences, syntax: syntax, table: table) { role, r in self.color(Palette.color(role), r) }

        colored = range
        passSeconds.append(Double(DispatchTime.now().uptimeNanoseconds - started) / 1e9)
    }

    /// Colours by the syntax of this file name (`SyntaxTable.name(forFileName:)`): the extension decides; a file no syntax claims is Markdown.
    func use(fileName: String?) {
        let wanted = table.syntaxes[table.name(forFileName: fileName)]
        guard wanted?.name != syntax?.name, let tv = textView, let storage = tv.textStorage else { return }
        syntax = wanted
        let ns = storage.mutableString
        fences = Highlighter.fenceLines(in: ns, from: 0, to: ns.length, markers: wanted?.fences?.markers ?? [])
        colored = NSRange(location: NSNotFound, length: 0)
        highlightNow()
    }

    /// End offset of a front matter at the very top of the text (0 if there is none): its first line is `open`, it ends with the first line after
    /// that starts with one of `close`, looked for within `scan` characters (the table's `frontMatter`).
    static func frontMatterEnd(_ ns: NSString, _ fm: SyntaxTable.FrontMatter) -> Int {
        let n = ns.length, open = (fm.open as NSString).length
        guard n > open, ns.substring(with: NSRange(location: 0, length: open)) == fm.open,
              ns.character(at: open) == 0x0A || ns.character(at: open) == 0x0D else { return 0 }
        let limit = min(n, open + fm.scan)
        var best = NSNotFound
        for closer in fm.close {
            let hit = ns.range(of: "\n" + closer, options: .literal, range: NSRange(location: open, length: limit - open))
            if hit.location != NSNotFound && (best == NSNotFound || hit.location < best) { best = hit.location }
        }
        guard best != NSNotFound else { return 0 }
        return NSMaxRange(ns.lineRange(for: NSRange(location: best + 1, length: 0)))
    }

    /// The colouring of the lines `lo..<hi` of `ns` (both at line starts) as (role, range) pairs, in the order they are painted: where two
    /// overlap the later one wins. `fences` are the offsets of the fence lines of the whole text. The editor paints these; the conformance smoke
    /// test (`--smoke-syntax`) collects them for the whole text and compares them with syntax/cases.json.
    static func pass(_ ns: NSString, lo: Int, hi: Int, fences: [Int], syntax: SyntaxTable.Syntax, table: SyntaxTable,
                     put: (String, NSRange) -> Void) {
        let frontEnd = syntax.frontMatter.map { frontMatterEnd(ns, $0) } ?? 0
        var cursor = lo
        if lo < frontEnd, let front = syntax.frontMatter, let inner = table.syntaxes[front.syntax] {
            let end = min(hi, frontEnd)
            apply(inner.rules, to: NSRange(location: lo, length: end - lo), ns, put)
            cursor = end
        }
        guard cursor < hi else { return }
        guard let fencing = syntax.fences else {
            apply(syntax.rules, to: NSRange(location: cursor, length: hi - cursor), ns, put)
            return
        }
        // fences are looked for after the front matter: the ones above it do not count (a fence line in a YAML value)
        let base = lowerBound(fences, frontEnd)
        var i = lowerBound(fences, cursor)
        var inCode = (i - base) % 2 == 1
        var opener: Int? = inCode ? fences[i - 1] : nil
        func segment(_ r: NSRange) {
            guard r.length > 0 else { return }
            guard inCode else { apply(syntax.rules, to: r, ns, put); return }
            // a fenced block: the rules of its language, else one role
            if let at = opener,
               let language = table.language(of: ns.substring(with: ns.lineRange(for: NSRange(location: at, length: 0))), in: syntax) {
                apply(language.rules, to: r, ns, put)
            } else { put(fencing.role, r) }
        }
        while i < fences.count && fences[i] < hi {
            let f = fences[i]
            segment(NSRange(location: cursor, length: f - cursor))
            let lineEnd = min(hi, NSMaxRange(ns.lineRange(for: NSRange(location: f, length: 0))))
            put(fencing.role, NSRange(location: f, length: lineEnd - f))
            if !inCode { opener = f }
            inCode.toggle()
            cursor = lineEnd
            i += 1
        }
        segment(NSRange(location: cursor, length: hi - cursor))
    }

    private static func apply(_ rules: [SyntaxTable.Rule], to seg: NSRange, _ ns: NSString, _ put: (String, NSRange) -> Void) {
        guard seg.length > 0 else { return }
        let sub = ns.substring(with: seg)   // a few tens of KB, whatever the document's size
        let whole = NSRange(location: 0, length: (sub as NSString).length)
        for rule in rules {
            rule.regex.enumerateMatches(in: sub, options: [], range: whole) { match, _, _ in
                guard let match, match.range.length > 0 else { return }
                if let role = rule.role { put(role, NSRange(location: seg.location + match.range.location, length: match.range.length)) }
                for (number, role) in rule.groups where number < match.numberOfRanges {
                    let g = match.range(at: number)
                    if g.location != NSNotFound && g.length > 0 { put(role, NSRange(location: seg.location + g.location, length: g.length)) }
                }
            }
        }
    }

    // MARK: where the colours go: layout-manager temporary attributes (TextKit 1) or rendering attributes (TextKit 2)

    private func textRange(_ r: NSRange, _ tlm: NSTextLayoutManager) -> NSTextRange? {
        let tcm = tlm.textContentManager!
        guard let s = tcm.location(tcm.documentRange.location, offsetBy: r.location),
              let e = tcm.location(s, offsetBy: r.length) else { return nil }
        return NSTextRange(location: s, end: e)
    }

    // Not called: NSTextLayoutManager.invalidateRenderingAttributes(for:) throws the colours away instead of
    // redrawing them (measured with the smoke test: 9089 coloured pixels before, 0 after). add/remove redraw by themselves.
    private func removeColors(_ r: NSRange) {
        guard let tv = textView else { return }
        if let tlm = tv.textLayoutManager {
            if let tr = textRange(r, tlm) { tlm.removeRenderingAttribute(.foregroundColor, for: tr) }
        } else {
            tv.layoutManager?.removeTemporaryAttribute(.foregroundColor, forCharacterRange: r)
        }
    }

    private func color(_ c: NSColor, _ r: NSRange) {
        guard r.length > 0, let tv = textView else { return }
        if let tlm = tv.textLayoutManager {
            if let tr = textRange(r, tlm) { tlm.addRenderingAttribute(.foregroundColor, value: c, for: tr) }
        } else {
            tv.layoutManager?.addTemporaryAttribute(.foregroundColor, value: c, forCharacterRange: r)
        }
    }
}
