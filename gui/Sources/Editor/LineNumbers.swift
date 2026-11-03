import Cocoa

/// The line numbers in the margin (CotEditor's, and what every code editor has): a vertical ruler beside the text. Only the
/// visible lines are numbered. The number of the first visible line is counted from an anchor (a position and its line
/// number) that is kept between draws, so scrolling by a screen or typing never counts from the top again; a jump far
/// away counts the distance once (about a millisecond per megabyte). A wrapped line is numbered once, on its first row.
/// Every number that changes the look is a setting (`lineNumbers`, `lineNumberMinDigits`, `lineNumberSizeDelta`,
/// `lineNumberOpacity`, `lineNumberPadding`).
final class LineNumberRuler: NSRulerView {
    /// One numbered row: the line number, where its text's baseline is (text view coordinates) and where its paragraph starts.
    struct Row: Equatable {
        let line: Int
        let baseline: CGFloat
        let location: Int
    }

    private weak var tv: NSTextView?
    private let stats: TextStats
    private var anchor = (loc: 0, line: 1)
    private var label = NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .regular)

    init(scroll: NSScrollView, textView: NSTextView, stats: TextStats) {
        self.tv = textView
        self.stats = stats
        super.init(scrollView: scroll, orientation: .verticalRuler)
        clientView = textView
        let center = NotificationCenter.default
        if let storage = textView.textStorage {
            center.addObserver(self, selector: #selector(edited(_:)), name: NSTextStorage.didProcessEditingNotification, object: storage)
        }
        center.addObserver(self, selector: #selector(redraw), name: NSTextView.didChangeSelectionNotification, object: textView)
        // A scroll is drawn by copying what was on screen and drawing only the strip that appeared; the numbers must not be
        // copied (they would be stale and cut), so every scroll, and every change of the text view's size (TextKit 2 settles
        // its estimated line heights while the text is drawn), invalidates the whole margin.
        scroll.contentView.postsBoundsChangedNotifications = true
        center.addObserver(self, selector: #selector(redraw), name: NSView.boundsDidChangeNotification, object: scroll.contentView)
        textView.postsFrameChangedNotifications = true
        center.addObserver(self, selector: #selector(redraw), name: NSView.frameDidChangeNotification, object: textView)
        stats.listen { [weak self] in self?.fitLater() }
        applySettings()
    }

    required init(coder: NSCoder) { fatalError("not used") }

    deinit { NotificationCenter.default.removeObserver(self) }

    @objc private func redraw() { setNeedsDisplay(bounds) }

    @objc private func edited(_ note: Notification) {
        guard let storage = note.object as? NSTextStorage, storage.editedMask.contains(.editedCharacters) else { return }
        if storage.editedRange.location < anchor.loc { anchor = (0, 1) }
        fitLater()
        needsDisplay = true
    }

    /// The font, colours and width again (a setting changed, or the text was replaced).
    func applySettings() {
        let base = editorFont()
        let size = max(6, base.pointSize - CGFloat(Settings.number("lineNumberSizeDelta")))
        label = NSFont(descriptor: base.fontDescriptor, size: size) ?? NSFont.monospacedDigitSystemFont(ofSize: size, weight: .regular)
        fit()
        needsDisplay = true
    }

    /// The text was replaced: nothing of the old anchor is valid.
    func reset() {
        anchor = (0, 1)
        fit()
        needsDisplay = true
    }

    private var padding: CGFloat { CGFloat(max(0, Settings.number("lineNumberPadding"))) }

    /// Changing the width lays the text out again, which is not allowed while the text storage is still being edited (the
    /// notifications that call this arrive in the middle of an edit): so it is done a moment later, once per burst.
    private var fitPending = false
    private func fitLater() {
        guard !fitPending else { return }
        fitPending = true
        DispatchQueue.main.async { [weak self] in
            self?.fitPending = false
            self?.fit()
        }
    }

    /// The width follows the number of digits of the last line (once it is counted), never fewer than `lineNumberMinDigits`.
    private func fit() {
        let digits = max(Settings.int("lineNumberMinDigits"), String(stats.lines ?? 0).count)
        let digitWidth = ("0" as NSString).size(withAttributes: [.font: label]).width
        let width = ceil(CGFloat(digits) * digitWidth + 2 * padding)
        if abs(ruleThickness - width) > 0.5 { ruleThickness = width }
    }

    // MARK: which lines are on the screen

    private func newlines(in range: NSRange, of ns: NSString) -> Int {
        let lb = stats.lineBreak
        var buffer = [unichar](repeating: 0, count: min(1 << 16, max(range.length, 1)))
        var position = range.location, total = 0
        while position < NSMaxRange(range) {
            let n = min(buffer.count, NSMaxRange(range) - position)
            ns.getCharacters(&buffer, range: NSRange(location: position, length: n))
            for i in 0..<n where buffer[i] == lb { total += 1 }
            position += n
        }
        return total
    }

    /// The line number of the paragraph that starts at `loc`, counted from the anchor (which moves there).
    private func lineNumber(at loc: Int, of ns: NSString) -> Int {
        let from = min(anchor.loc, ns.length), to = min(loc, ns.length)
        let n = newlines(in: NSRange(location: min(from, to), length: abs(to - from)), of: ns)
        let line = to >= from ? anchor.line + n : anchor.line - n
        anchor = (to, line)
        return line
    }

    /// The numbered rows now on the screen, top to bottom. This is what is drawn (and what the smoke test checks).
    func visibleRows() -> [Row] {
        guard let tv, let storage = tv.textStorage else { return [] }
        let ns = storage.mutableString
        let origin = tv.textContainerOrigin
        let rect = tv.visibleRect.offsetBy(dx: -origin.x, dy: -origin.y)
        var rows: [Row] = []
        func add(_ location: Int, _ baseline: CGFloat) {
            rows.append(Row(line: lineNumber(at: location, of: ns), baseline: baseline + origin.y, location: location))
        }
        if let tlm = tv.textLayoutManager, let tcm = tlm.textContentManager {   // TextKit 2
            // asked of the scroll position, like the highlighter does (the layout controller's viewport lags behind a scroll)
            let start = tlm.textLayoutFragment(for: CGPoint(x: 1, y: max(0, rect.minY)))?.rangeInElement.location ?? tcm.documentRange.location
            var stoppedEarly = false
            var last: (maxY: CGFloat, lastBaseline: CGFloat)?   // the last fragment's bottom, and where its last line's baseline is
            tlm.enumerateTextLayoutFragments(from: start, options: [.ensuresLayout]) { fragment in
                let frame = fragment.layoutFragmentFrame
                if frame.minY > rect.maxY { stoppedEarly = true; return false }
                let location = tcm.offset(from: tcm.documentRange.location, to: fragment.rangeInElement.location)
                if let line = fragment.textLineFragments.first {
                    add(location, frame.minY + line.typographicBounds.minY + line.glyphOrigin.y)
                    let end = fragment.textLineFragments.last ?? line   // the empty last line is part of the last fragment's frame
                    last = (frame.maxY, frame.minY + end.typographicBounds.minY + end.glyphOrigin.y)
                }
                return true
            }
            // the empty last line after a final line break (or the only line of an empty text) has no fragment of its own
            let endsInBreak = ns.length == 0 || ns.paragraphRange(for: NSRange(location: ns.length, length: 0)).location == ns.length
            if endsInBreak, !stoppedEarly, rows.last?.location != ns.length {
                let ascent = (tv.font ?? label).ascender
                let baseline = last?.lastBaseline ?? ascent
                if baseline - ascent <= rect.maxY, baseline + ascent >= rect.minY { add(ns.length, baseline) }
            }
        } else if let lm = tv.layoutManager, let container = tv.textContainer {   // TextKit 1
            let glyphs = lm.glyphRange(forBoundingRect: rect, in: container)
            lm.enumerateLineFragments(forGlyphRange: glyphs) { lineRect, _, _, glyphRange, _ in
                let chars = lm.characterRange(forGlyphRange: glyphRange, actualGlyphRange: nil)
                guard chars.location <= ns.length, ns.paragraphRange(for: NSRange(location: chars.location, length: 0)).location == chars.location else { return }
                add(chars.location, lineRect.minY + lm.location(forGlyphAt: glyphRange.location).y)
            }
            let extra = lm.extraLineFragmentRect
            if extra.height > 0, extra.intersects(rect) {   // the empty last line after a final line break
                add(ns.length, extra.minY + (tv.font?.ascender ?? label.ascender))
            }
        }
        // the anchor stays at the first row, so the next scroll by a little counts a little
        if let first = rows.first { anchor = (first.location, first.line) }
        return rows
    }

    // MARK: drawing

    override func drawHashMarksAndLabels(in rect: NSRect) {
        Palette.background.setFill()
        bounds.fill()
        guard let tv, let ns = tv.textStorage?.mutableString else { return }
        let rows = visibleRows()
        let caret = ns.paragraphRange(for: NSRange(location: min(tv.selectedRange().location, ns.length), length: 0)).location
        let opacity = CGFloat(min(100, max(0, Settings.number("lineNumberOpacity")))) / 100
        for row in rows {
            let ink = Palette.text.withAlphaComponent(row.location == caret ? 1 : opacity)
            let text = NSAttributedString(string: String(row.line), attributes: [.font: label, .foregroundColor: ink])
            let baseline = convert(NSPoint(x: 0, y: row.baseline), from: tv).y
            let y = isFlipped ? baseline - label.ascender : baseline + label.descender
            text.draw(at: NSPoint(x: bounds.width - padding - text.size().width, y: y))
        }
    }
}
