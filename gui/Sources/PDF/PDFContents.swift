import Cocoa
import PDFKit

/// The sidebar's table-of-contents mode: the PDF's outline as a tree, in the place of the thumbnails. A click goes to the entry; the
/// entry of the page being read is selected and its parents are opened. A PDF without an outline says so.
final class PDFContentsView: NSObject, NSOutlineViewDataSource, NSOutlineViewDelegate {
    let view = NSView()
    var onGo: ((PDFDestination) -> Void)?

    /// Only the visible mode pays for the tree: a document given while the mode is off is loaded when it is switched on.
    var isActive = false {
        didSet {
            guard isActive != oldValue, isActive else { return }
            loadIfNeeded()
            if let page = lastPage { reveal(page: page, force: true) }
        }
    }

    private let scroll = NSScrollView()
    private let outline = NSOutlineView()
    private let empty = NSTextField(labelWithString: "No table of contents")
    private var document: PDFDocument?
    private var root: PDFOutline?
    private var entries: [PDFOutline]?
    private var pages: [ObjectIdentifier: Int] = [:]   // -1 = no destination
    private var pending: (keepOpen: Bool, levels: Int)?
    private var syncing = false
    private var lastPage: Int?
    private var lastClick = Date.distantPast
    private static let cellID = NSUserInterfaceItemIdentifier("pdfmdedit.contents.cell")

    override init() {
        super.init()
        let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("title"))
        column.resizingMask = .autoresizingMask
        outline.addTableColumn(column)
        outline.outlineTableColumn = column
        outline.headerView = nil
        outline.style = .plain
        outline.indentationPerLevel = 12
        outline.rowHeight = 22
        outline.backgroundColor = Desk.color
        outline.autoresizesOutlineColumn = false
        outline.columnAutoresizingStyle = .uniformColumnAutoresizingStyle
        outline.dataSource = self
        outline.delegate = self
        outline.target = self
        outline.action = #selector(clicked(_:))
        scroll.documentView = outline
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        scroll.drawsBackground = true
        scroll.backgroundColor = Desk.color
        empty.textColor = .secondaryLabelColor
        empty.alignment = .center
        empty.isHidden = true
        for v in [scroll, empty] {
            v.translatesAutoresizingMaskIntoConstraints = false
            view.addSubview(v)
        }
        NSLayoutConstraint.activate([
            scroll.leadingAnchor.constraint(equalTo: view.leadingAnchor), scroll.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            scroll.topAnchor.constraint(equalTo: view.topAnchor), scroll.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            empty.centerXAnchor.constraint(equalTo: view.centerXAnchor), empty.topAnchor.constraint(equalTo: view.topAnchor, constant: 24),
            empty.leadingAnchor.constraint(greaterThanOrEqualTo: view.leadingAnchor, constant: 8),
        ])
    }

    /// A new document (or the same file read again: `keepOpen` puts the open entries back where they were).
    func use(_ doc: PDFDocument, keepOpen: Bool, levels: Int) {
        document = doc
        entries = nil
        pages = [:]
        pending = (keepOpen, levels)
        if isActive { loadIfNeeded() }
    }

    private func loadIfNeeded() {
        guard let doc = document, let (keepOpen, levels) = pending else { return }
        pending = nil
        let keys = keepOpen ? expandedKeys() : []
        root = doc.outlineRoot
        outline.reloadData()
        let has = (root?.numberOfChildren ?? 0) > 0
        empty.isHidden = has
        scroll.isHidden = !has
        guard has, let root else { return }
        if keepOpen, !keys.isEmpty { reopen(root, keys: keys) } else { open(root, depth: 0, levels: levels) }
    }

    // MARK: open entries

    /// An entry's place in the tree, as the indexes from the top ("0.3.1"), which survives a reload of the same file.
    private func key(_ item: PDFOutline) -> String {
        var parts: [Int] = []
        var cur = item
        while let parent = cur.parent {
            parts.append(cur.index)
            cur = parent
        }
        return parts.reversed().map(String.init).joined(separator: ".")
    }

    private func expandedKeys() -> Set<String> {
        var keys = Set<String>()
        for row in 0..<outline.numberOfRows {
            if let item = outline.item(atRow: row) as? PDFOutline, outline.isItemExpanded(item) { keys.insert(key(item)) }
        }
        return keys
    }

    private func reopen(_ node: PDFOutline, keys: Set<String>) {
        for i in 0..<node.numberOfChildren {
            guard let child = node.child(at: i), keys.contains(key(child)) else { continue }
            outline.expandItem(child)
            reopen(child, keys: keys)
        }
    }

    /// `levels` levels are shown when a file is opened: 1 = only the top entries, 2 = their children too.
    private func open(_ node: PDFOutline, depth: Int, levels: Int) {
        guard depth < levels - 1 else { return }
        for i in 0..<node.numberOfChildren {
            guard let child = node.child(at: i), child.numberOfChildren > 0 else { continue }
            outline.expandItem(child)
            open(child, depth: depth + 1, levels: levels)
        }
    }

    // MARK: following the page being read

    /// All entries in document order, without their pages: finding a page costs about a millisecond an entry (2600 entries on a
    /// 4000-page manual took 2 s), so a page is looked up only for the entries that are asked about, and kept.
    private func allEntries() -> [PDFOutline] {
        if let entries { return entries }
        var list: [PDFOutline] = []
        func walk(_ node: PDFOutline) {
            for i in 0..<node.numberOfChildren {
                guard let child = node.child(at: i) else { continue }
                list.append(child)
                walk(child)
            }
        }
        if let root { walk(root) }
        entries = list
        return list
    }

    private func pageIndex(of item: PDFOutline) -> Int? {
        let id = ObjectIdentifier(item)
        if let known = pages[id] { return known >= 0 ? known : nil }
        var index = -1
        if let page = item.destination?.page, let doc = document { index = doc.index(for: page) }
        pages[id] = index
        return index >= 0 ? index : nil
    }

    /// The last entry that starts on this page or before it. An outline is in the order of the document, so it is a binary search
    /// (about a dozen page look-ups); entries with no destination are stepped over.
    private func entry(forPage page: Int) -> PDFOutline? {
        let all = allEntries()
        var lo = 0, hi = all.count - 1
        var best: PDFOutline?
        while lo <= hi {
            let mid = (lo + hi) / 2
            var m = mid
            while m <= hi, pageIndex(of: all[m]) == nil { m += 1 }
            if m > hi { hi = mid - 1; continue }
            if pageIndex(of: all[m])! <= page { best = all[m]; lo = m + 1 } else { hi = mid - 1 }
        }
        return best
    }

    /// Selects the entry the page belongs to. The entry already selected stays when it starts on this very page (two sections on
    /// a page: the one that was clicked is not taken away).
    func reveal(page: Int, force: Bool = false) {
        lastPage = page
        guard isActive, pending == nil, root != nil, Date().timeIntervalSince(lastClick) > 0.6 || force else { return }
        if !force, let selected = outline.item(atRow: outline.selectedRow) as? PDFOutline, pageIndex(of: selected) == page { return }
        guard let best = entry(forPage: page) else { return }
        syncing = true
        var parents: [PDFOutline] = []
        var cur = best.parent
        while let p = cur, p.parent != nil { parents.append(p); cur = p.parent }
        for p in parents.reversed() { outline.expandItem(p) }
        let row = outline.row(forItem: best)
        if row >= 0 {
            outline.selectRowIndexes(IndexSet(integer: row), byExtendingSelection: false)
            outline.scrollRowToVisible(row)
        }
        syncing = false
    }

    // MARK: going to an entry

    @objc private func clicked(_ sender: Any?) { go(row: outline.clickedRow) }

    /// What a click on a row does.
    func go(row: Int) {
        guard row >= 0, let item = outline.item(atRow: row) as? PDFOutline, let destination = item.destination else { return }
        lastClick = Date()
        onGo?(destination)
    }

    // for the self-test
    var rowCount: Int { outline.numberOfRows }
    func page(ofRow row: Int) -> Int? {
        guard let item = outline.item(atRow: row) as? PDFOutline else { return nil }
        return pageIndex(of: item)
    }
    var emptyMessageShown: Bool { !empty.isHidden }
    var selectedPage: Int? {
        guard let selected = outline.item(atRow: outline.selectedRow) as? PDFOutline else { return nil }
        return pageIndex(of: selected)
    }

    func outlineViewSelectionDidChange(_ notification: Notification) {
        // the arrow keys move the selection and the page follows; a click is handled by `clicked`
        guard !syncing, NSApp.currentEvent?.type == .keyDown, let item = outline.item(atRow: outline.selectedRow) as? PDFOutline,
              let destination = item.destination else { return }
        lastClick = Date()
        onGo?(destination)
    }

    // MARK: data

    func outlineView(_ outlineView: NSOutlineView, numberOfChildrenOfItem item: Any?) -> Int {
        ((item as? PDFOutline) ?? root)?.numberOfChildren ?? 0
    }

    func outlineView(_ outlineView: NSOutlineView, child index: Int, ofItem item: Any?) -> Any {
        ((item as? PDFOutline) ?? root)!.child(at: index)!
    }

    func outlineView(_ outlineView: NSOutlineView, isItemExpandable item: Any) -> Bool { ((item as? PDFOutline)?.numberOfChildren ?? 0) > 0 }

    func outlineView(_ outlineView: NSOutlineView, viewFor tableColumn: NSTableColumn?, item: Any) -> NSView? {
        let label = (item as? PDFOutline)?.label ?? ""
        let cell: NSTableCellView
        if let reused = outlineView.makeView(withIdentifier: Self.cellID, owner: self) as? NSTableCellView {
            cell = reused
        } else {
            cell = NSTableCellView()
            cell.identifier = Self.cellID
            let field = NSTextField(labelWithString: "")
            field.font = .systemFont(ofSize: 12)
            field.lineBreakMode = .byTruncatingTail
            field.translatesAutoresizingMaskIntoConstraints = false
            cell.addSubview(field)
            cell.textField = field
            NSLayoutConstraint.activate([
                field.leadingAnchor.constraint(equalTo: cell.leadingAnchor, constant: 2),
                field.trailingAnchor.constraint(equalTo: cell.trailingAnchor, constant: -4),
                field.centerYAnchor.constraint(equalTo: cell.centerYAnchor),
            ])
        }
        cell.textField?.stringValue = label
        cell.textField?.toolTip = label   // a narrow sidebar cuts long titles
        return cell
    }
}
