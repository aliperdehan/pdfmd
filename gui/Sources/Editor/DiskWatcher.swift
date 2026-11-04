import Cocoa

/// Follows one file on disk: calls `onChange` (on the main thread, after a short pause so that a burst of writes is one call) when another
/// program wrote, renamed over or deleted it. A program that saves by writing a new file and renaming it over the old one leaves this
/// watcher on the old file, so after a rename or a delete it opens the new one.
final class DiskWatcher {
    private let url: URL
    private let onChange: () -> Void
    private var source: DispatchSourceFileSystemObject?
    private var pending: DispatchWorkItem?

    init(url: URL, onChange: @escaping () -> Void) {
        self.url = url
        self.onChange = onChange
        watch()
    }

    deinit { stop() }

    func stop() {
        pending?.cancel(); pending = nil
        source?.cancel(); source = nil
    }

    private func watch() {
        source?.cancel(); source = nil
        let fd = open(url.path, O_EVTONLY)
        guard fd >= 0 else { return }
        let s = DispatchSource.makeFileSystemObjectSource(fileDescriptor: fd, eventMask: [.write, .extend, .attrib, .rename, .delete], queue: .main)
        s.setEventHandler { [weak self, weak s] in self?.fired(replaced: s?.data.contains(.rename) == true || s?.data.contains(.delete) == true) }
        s.setCancelHandler { close(fd) }
        s.resume()
        source = s
    }

    private func fired(replaced: Bool) {
        pending?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            if replaced { self.watch() }
            self.onChange()
        }
        pending = work
        DispatchQueue.main.asyncAfter(deadline: .now() + Settings.number("diskChangeDelayMs") / 1000, execute: work)
    }
}
